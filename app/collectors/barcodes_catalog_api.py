"""
Опциональное обогащение (Tier B) через публичный API barcodes-catalog.ru.

Внимание: хостинг API часто защищён Cloudflare (JS-challenge). Запросы без
полноценного браузера (headless collector) могут получать не JSON, а страницу
проверки — не используйте этот модуль в автоматическом ETL-pipeline.

Ручной/экспериментальный вызов: включите ``ENABLE_BARCODES_CATALOG_API`` и
вызывайте ``enrich_offers_gaps_from_api`` из скрипта, не из ``collect_all_data``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Mapping, Optional, cast

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.collectors.compat_env import env_int
from app.database import NormalizedOffer
from app.ml.matching import normalize_barcode

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.barcodes-catalog.ru"


def _enabled() -> bool:
    return os.getenv("ENABLE_BARCODES_CATALOG_API", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _rate_delay_sec() -> float:
    raw = (os.getenv("BARCODES_CATALOG_API_RPS") or "0.5").strip()
    try:
        rps = float(raw)
    except ValueError:
        rps = 0.5
    if rps <= 0:
        return 0.0
    return 1.0 / rps


def _lookup_free_search(barcode: str) -> Optional[Mapping[str, Any]]:
    """
    Выполняет GET free_search для одного штрихкода.

    Может стабильно ломаться из-за Cloudflare при не-браузерных клиентах.
    """
    base = (os.getenv("BARCODES_CATALOG_API_BASE") or _DEFAULT_BASE).rstrip("/")
    url = f"{base}/barcode/free_search"
    try:
        r = requests.get(
            url,
            params={"barcode": barcode, "limit": 1},
            timeout=(5, 15),
            headers={"User-Agent": "PriceDesk-Collector/1.0"},
        )
        r.raise_for_status()
        return cast(Mapping[str, Any], r.json())
    except (requests.RequestException, ValueError, OSError) as e:
        logger.debug("barcodes-catalog: %s: %s", barcode, e)
        return None


def enrich_offers_gaps_from_api(session: Session) -> int:
    """
    Для офферов с заполненным штрихкодом и пустыми brand/vendor пытается дозаполнить по API.

    Ограничение по числу вызовов за проход: ``BARCODES_CATALOG_API_MAX_CALLS`` (40 по умолчанию).

    Returns:
        Число обновлённых офферов.
    """
    if not _enabled():
        return 0
    cap = env_int("BARCODES_CATALOG_API_MAX_CALLS", 40)
    if cap <= 0:
        return 0
    delay = _rate_delay_sec()
    rows = session.scalars(
        select(NormalizedOffer).where(
            NormalizedOffer.barcode.isnot(None),
            or_(
                NormalizedOffer.brand.is_(None),
                NormalizedOffer.vendor_code.is_(None),
            ),
        )
    ).all()
    updated = 0
    calls = 0
    for o in rows:
        if calls >= cap:
            break
        bc = normalize_barcode(o.barcode)
        if not bc:
            continue
        if delay > 0 and calls:
            time.sleep(delay)
        data = _lookup_free_search(bc)
        calls += 1
        if not data:
            continue
        # API может отдавать { data: { product_name, ... } } или плоскую структуру
        payload: Mapping[str, Any] = data
        if "data" in data and isinstance(data["data"], dict):
            payload = data["data"]
        name = (payload.get("product_name") or payload.get("name") or payload.get("title") or "")
        brand = (payload.get("brand") or payload.get("brand_name") or payload.get("vendor") or "")
        art = (payload.get("article") or payload.get("article_number") or payload.get("code") or "")
        changed = False
        if (not o.vendor_code or not str(o.vendor_code).strip()) and art:
            o.vendor_code = str(art).strip()[:128]
            changed = True
        if (not o.brand or not str(o.brand).strip()) and brand:
            o.brand = str(brand).strip()[:200]
            changed = True
        if (not o.name or not str(o.name).strip()) and name:
            o.name = str(name).strip()[:500]
            changed = True
        if changed:
            updated += 1
    if updated:
        session.flush()
        logger.info("barcodes_catalog_api: обогащено офферов: %s (вызовов API: %s)", updated, calls)
    return updated
