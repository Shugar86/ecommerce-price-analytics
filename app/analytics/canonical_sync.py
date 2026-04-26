"""
Связывание normalized_offers с canonical_products через exact-first правила match_pair.

Кластеризация: только совпадения с is_automated=True (без fuzzy TF-IDF).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import DefaultDict

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.database import CanonicalProduct, NormalizedOffer
from app.ml.matching import (
    extract_model,
    match_pair,
    norm_brand,
    normalize_barcode,
    norm_vendor_code,
)

logger = logging.getLogger(__name__)


class _DSU:
    """Disjoint Set Union для индексов офферов."""

    def __init__(self, n: int) -> None:
        """Инициализирует n элементов."""
        self._p = list(range(n))

    def find(self, x: int) -> int:
        """Находит корень с сжатием путей."""
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a: int, b: int) -> None:
        """Объединяет классы эквивалентности a и b."""
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._p[rb] = ra


def _distinct_sources(indices: list[int], offers: list[NormalizedOffer]) -> set[str]:
    """Множество имён источников для списка индексов."""
    return {offers[i].source_name for i in indices if offers[i].source_name}


def _union_if_automated(
    dsu: _DSU,
    i: int,
    j: int,
    offers: list[NormalizedOffer],
) -> bool:
    """Union(i,j), если match_pair даёт автоматическое совпадение."""
    res = match_pair(offers[i], offers[j])
    if res is None or not res.is_automated:
        return False
    dsu.union(i, j)
    return True


def _add_barcode_clusters(dsu: _DSU, offers: list[NormalizedOffer]) -> None:
    """Объединяет офферы с одинаковым нормализованным штрихкодом (2+ источника)."""
    buckets: DefaultDict[str, list[int]] = defaultdict(list)
    for i, o in enumerate(offers):
        bc = normalize_barcode(o.barcode)
        if bc:
            buckets[bc].append(i)
    for _bc, inds in buckets.items():
        if len(_distinct_sources(inds, offers)) < 2:
            continue
        head = inds[0]
        for j in inds[1:]:
            dsu.union(head, j)


def _add_vendor_brand_clusters(dsu: _DSU, offers: list[NormalizedOffer]) -> None:
    """Объединяет по (vendor_code, brand), если оба поля непусты и 2+ источника."""
    buckets: DefaultDict[tuple[str, str], list[int]] = defaultdict(list)
    for i, o in enumerate(offers):
        v = norm_vendor_code(o.vendor_code)
        b = norm_brand(o.brand)
        if not v or not b:
            continue
        buckets[(v, b)].append(i)
    for _key, inds in buckets.items():
        if len(_distinct_sources(inds, offers)) < 2:
            continue
        head = inds[0]
        for j in inds[1:]:
            dsu.union(head, j)


def _add_brand_model_clusters(dsu: _DSU, offers: list[NormalizedOffer]) -> None:
    """Объединяет по (brand, extract_model(name)) при 2+ источниках."""
    buckets: DefaultDict[tuple[str, str], list[int]] = defaultdict(list)
    for i, o in enumerate(offers):
        b = norm_brand(o.brand)
        m = extract_model(o.name)
        if not b or not m:
            continue
        buckets[(b, m)].append(i)
    for _key, inds in buckets.items():
        if len(_distinct_sources(inds, offers)) < 2:
            continue
        head = inds[0]
        for j in inds[1:]:
            dsu.union(head, j)


def _add_vendor_category_pairs(dsu: _DSU, offers: list[NormalizedOffer]) -> None:
    """Попарно: тот же артикул + совместимая категория, разные источники."""
    by_vendor: DefaultDict[str, list[int]] = defaultdict(list)
    for i, o in enumerate(offers):
        v = norm_vendor_code(o.vendor_code)
        if not v:
            continue
        by_vendor[v].append(i)
    for _v, inds in by_vendor.items():
        if len(inds) < 2:
            continue
        n = len(inds)
        for a in range(n):
            for b in range(a + 1, n):
                ia, ib = inds[a], inds[b]
                if offers[ia].source_name == offers[ib].source_name:
                    continue
                _union_if_automated(dsu, ia, ib, offers)


def _component_confidence(comp: list[NormalizedOffer]) -> float:
    """Максимальная уверенность по автоматическим парам внутри компоненты."""
    best = 0.0
    n = len(comp)
    for i in range(n):
        for j in range(i + 1, n):
            m = match_pair(comp[i], comp[j])
            if m is not None and m.is_automated and m.confidence > best:
                best = m.confidence
    return best if best > 0 else 0.8


def _pick_canonical_fields(comp: list[NormalizedOffer]) -> dict[str, object]:
    """Агрегирует поля карточки из офферов компоненты."""
    names = [str(o.name) for o in comp if o.name]
    canonical_name = max(names, key=len) if names else None
    brand = next((o.brand for o in comp if o.brand), None)
    vendor_code = next((o.vendor_code for o in comp if o.vendor_code), None)
    barcode = next((o.barcode for o in comp if o.barcode), None)
    category = next((o.category for o in comp if o.category), None)
    return {
        "canonical_name": (canonical_name[:500] if canonical_name else None),
        "brand": (brand[:200] if brand else None),
        "vendor_code": (vendor_code[:128] if vendor_code else None),
        "barcode": (str(barcode)[:128] if barcode else None),
        "category": (str(category)[:200] if category else None),
    }


def rebuild_canonical_from_normalized(session: Session) -> int:
    """
    Пересобирает canonical_products и ссылки normalized_offers.

    Использует только автоматические правила из ``match_pair`` (штрихкод, бренд+артикул,
    артикул+категория, бренд+модель и попарное уточнение). Fuzzy TF-IDF в кластеры не входит.

    Returns:
        Число созданных canonical_products.
    """
    session.execute(
        update(NormalizedOffer).values(canonical_product_id=None)
    )
    session.execute(delete(CanonicalProduct))
    session.flush()

    offers = list(
        session.scalars(select(NormalizedOffer).order_by(NormalizedOffer.id)).all()
    )
    if not offers:
        session.commit()
        logger.info("canonical: нет normalized_offers")
        return 0

    n = len(offers)
    dsu = _DSU(n)

    _add_barcode_clusters(dsu, offers)
    _add_vendor_brand_clusters(dsu, offers)
    _add_brand_model_clusters(dsu, offers)
    _add_vendor_category_pairs(dsu, offers)

    components: DefaultDict[int, list[int]] = defaultdict(list)
    for i in range(n):
        components[dsu.find(i)].append(i)

    new_canonical = 0
    for _root, inds in components.items():
        if len(_distinct_sources(inds, offers)) < 2:
            continue
        comp_offers = [offers[i] for i in inds]
        fields = _pick_canonical_fields(comp_offers)
        conf = _component_confidence(comp_offers)
        cp = CanonicalProduct(
            canonical_name=fields["canonical_name"],  # type: ignore[arg-type]
            brand=fields["brand"],  # type: ignore[arg-type]
            vendor_code=fields["vendor_code"],  # type: ignore[arg-type]
            barcode=fields["barcode"],  # type: ignore[arg-type]
            category=fields["category"],  # type: ignore[arg-type]
            match_confidence=float(conf),
            created_at=datetime.utcnow(),
        )
        session.add(cp)
        session.flush()
        new_canonical += 1
        for i in inds:
            offers[i].canonical_product_id = cp.id

    session.commit()
    logger.info("canonical: новых canonical_products: %s", new_canonical)
    return new_canonical
