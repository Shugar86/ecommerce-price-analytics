"""
Обогащение normalized_offers из таблицы barcode_reference (Tier B).
"""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import BarcodeReference, NormalizedOffer
from app.ml.matching import normalize_barcode

logger = logging.getLogger(__name__)


def enrich_normalized_offers_from_reference(session: Session) -> int:
    """
    Подставляет vendor_code и brand из справочника, если в оффере пусто.

    Args:
        session: Сессия БД.

    Returns:
        Число офферов, у которых изменились поля (после flush).
    """
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
    for o in rows:
        bc = normalize_barcode(o.barcode)
        if not bc:
            continue
        ref = session.execute(
            select(BarcodeReference).where(BarcodeReference.barcode == bc)
        ).scalar_one_or_none()
        if ref is None:
            continue
        changed = False
        if (not o.vendor_code or not str(o.vendor_code).strip()) and ref.article:
            o.vendor_code = str(ref.article).strip()[:128]
            changed = True
        if (not o.brand or not str(o.brand).strip()) and ref.vendor:
            o.brand = str(ref.vendor).strip()[:200]
            changed = True
        if changed:
            updated += 1
    if updated:
        session.flush()
        logger.info("barcode_reference: обогащено офферов: %s", updated)
    return updated
