"""
Aggregates for field completeness and exact-key overlap between shops.

Logic mirrors the CLI overlap report, exposed for the web dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Product


@dataclass(frozen=True)
class ShopCompletenessRow:
    """Per-source counts and fill rates for identifier columns.

    Attributes:
        source_shop: Value of ``Product.source_shop``.
        total: Row count for that shop.
        with_barcode: Rows with non-empty ``barcode``.
        with_vendor_code: Rows with non-empty ``vendor_code``.
        with_category_id: Rows with non-empty ``category_id``.
        with_name_norm: Rows with non-empty ``name_norm``.
    """

    source_shop: str
    total: int
    with_barcode: int
    with_vendor_code: int
    with_category_id: int
    with_name_norm: int

    def pct(self, n: int) -> float:
        """Return percentage of ``total`` represented by ``n``, rounded to one decimal."""
        if self.total <= 0:
            return 0.0
        return round(100.0 * float(n) / float(self.total), 1)


@dataclass(frozen=True)
class ShopPairKeyOverlap:
    """Exact intersection size for a key column between two sources.

    Attributes:
        shop_a: First ``source_shop`` (lexicographic pair from ``combinations``).
        shop_b: Second ``source_shop``.
        field: Column name: ``barcode``, ``vendor_code``, or ``name_norm``.
        overlap_count: ``len(set_a & set_b)`` for that field.
    """

    shop_a: str
    shop_b: str
    field: str
    overlap_count: int


def _fetch_keyset(session: Session, shop: str, field: str) -> set[str]:
    """Load distinct non-empty key values for one shop and Product column name."""
    col = getattr(Product, field)
    rows = session.execute(
        select(col).where(Product.source_shop == shop, col.is_not(None))
    ).all()
    return {str(r[0]) for r in rows if r and r[0]}


def _shop_completeness(session: Session, shop: str) -> ShopCompletenessRow:
    """Field completeness for a single ``source_shop``."""
    rows = session.execute(
        select(Product.barcode, Product.vendor_code, Product.category_id, Product.name_norm).where(
            Product.source_shop == shop
        )
    ).all()
    total = len(rows)
    w_bar = sum(1 for b, _, _, _ in rows if b)
    w_ven = sum(1 for _, v, _, _ in rows if v)
    w_cat = sum(1 for _, _, c, _ in rows if c)
    w_nn = sum(1 for _, _, _, n in rows if n)
    return ShopCompletenessRow(
        source_shop=shop,
        total=total,
        with_barcode=w_bar,
        with_vendor_code=w_ven,
        with_category_id=w_cat,
        with_name_norm=w_nn,
    )


def _fetch_shops_ordered(session: Session) -> list[str]:
    """Distinct shop names, stable order (alphabetical)."""
    rows = session.execute(
        select(Product.source_shop)
        .group_by(Product.source_shop)
        .order_by(Product.source_shop)
    ).scalars()
    return [s for s in rows if s]


def build_quality_dashboard_slice(
    session: Session,
    *,
    max_pair_rows: int = 24,
) -> dict[str, Any]:
    """Context fragment for the dashboard: completeness table + key overlaps.

    Args:
        session: Open ORM session.
        max_pair_rows: Cap on pairwise overlap rows (each row is one shop pair and field).

    Returns:
        Dict with ``shop_completeness``, ``key_overlaps``, and ``shops_loaded``.
    """
    shops = _fetch_shops_ordered(session)
    shop_completeness = [_shop_completeness(session, s) for s in shops]

    # Preload key sets for exact intersection (barcode, vendor_code, name_norm)
    keysets: dict[tuple[str, str], set[str]] = {}
    for s in shops:
        for field in ("barcode", "vendor_code", "name_norm"):
            keysets[(s, field)] = _fetch_keyset(session, s, field)

    overlaps: list[ShopPairKeyOverlap] = []
    for a, b in combinations(shops, 2):
        for field, label in (
            ("barcode", "barcode"),
            ("vendor_code", "vendor_code"),
            ("name_norm", "name_norm"),
        ):
            n = len(keysets[(a, field)] & keysets[(b, field)])
            overlaps.append(ShopPairKeyOverlap(shop_a=a, shop_b=b, field=label, overlap_count=n))

    overlaps.sort(key=lambda o: o.overlap_count, reverse=True)
    return {
        "shops_loaded": shops,
        "shop_completeness": shop_completeness,
        "key_overlaps": overlaps[:max_pair_rows],
    }
