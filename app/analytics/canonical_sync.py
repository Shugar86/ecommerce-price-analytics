"""
Связывание normalized_offers с canonical_products по артикулу и мульти-источнику.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import CanonicalProduct, NormalizedOffer

logger = logging.getLogger(__name__)


def rebuild_canonical_from_normalized(session: Session) -> int:
    """
    Создаёт canonical по (vendor_code, brand), если встречается в 2+ источниках.

    Назначает ``normalized_offers.canonical_product_id`` для соответствующих строк.

    Returns:
        Число новых canonical_products.
    """
    pairs = session.execute(
        select(
            func.upper(NormalizedOffer.vendor_code),
            func.coalesce(
                func.upper(NormalizedOffer.brand), ""
            ),
            func.count(
                func.distinct(NormalizedOffer.source_name)
            ).label("n_src"),
        )
        .where(
            NormalizedOffer.vendor_code.isnot(None), NormalizedOffer.vendor_code != ""
        )
        .group_by(1, 2)
        .having(func.count(func.distinct(NormalizedOffer.source_name)) >= 2)
    ).all()

    new_canonical = 0
    for v_key, b_key, _n in pairs:
        v_key = (v_key or "").strip()
        b_key = (b_key or "").strip()

        ex = session.execute(
            select(CanonicalProduct)
            .where(
                func.upper(CanonicalProduct.vendor_code) == v_key,
                func.coalesce(
                    func.upper(CanonicalProduct.brand), ""
                ) == b_key,
            )
            .limit(1)
        ).scalar_one_or_none()

        if ex is not None:
            cp = ex
        else:
            name_sample = session.scalar(
                select(NormalizedOffer.name)
                .where(
                    func.upper(NormalizedOffer.vendor_code) == v_key,
                    func.coalesce(
                        func.upper(NormalizedOffer.brand), ""
                    ) == b_key,
                )
                .limit(1)
            )
            bc_sample = session.scalar(
                select(NormalizedOffer.barcode)
                .where(
                    func.upper(NormalizedOffer.vendor_code) == v_key,
                    func.coalesce(
                        func.upper(NormalizedOffer.brand), ""
                    ) == b_key,
                    NormalizedOffer.barcode.isnot(None),
                )
                .limit(1)
            )
            cat_sample = session.scalar(
                select(NormalizedOffer.category)
                .where(
                    func.upper(NormalizedOffer.vendor_code) == v_key,
                    func.coalesce(
                        func.upper(NormalizedOffer.brand), ""
                    ) == b_key,
                    NormalizedOffer.category.isnot(None),
                )
                .limit(1)
            )
            brand_s = b_key if b_key else None
            if brand_s and len(brand_s) > 200:
                brand_s = brand_s[:200]
            cp = CanonicalProduct(
                canonical_name=(str(name_sample)[:500] if name_sample else None),
                brand=brand_s,
                vendor_code=session.execute(
                    select(NormalizedOffer.vendor_code)
                    .where(
                        func.upper(NormalizedOffer.vendor_code) == v_key,
                        func.coalesce(
                            func.upper(NormalizedOffer.brand), ""
                        ) == b_key,
                    )
                    .limit(1)
                ).scalar_one()[:128],
                barcode=(str(bc_sample)[:128] if bc_sample else None),
                category=(str(cat_sample)[:200] if cat_sample else None),
                match_confidence=0.8,
                created_at=datetime.utcnow(),
            )
            session.add(cp)
            session.flush()
            new_canonical += 1

        session.execute(
            update(NormalizedOffer)
            .where(
                func.upper(NormalizedOffer.vendor_code) == v_key,
                func.coalesce(
                    func.upper(NormalizedOffer.brand), ""
                ) == b_key,
            )
            .values(canonical_product_id=cp.id)
        )

    session.commit()
    logger.info("canonical: новых canonical_products: %s", new_canonical)
    return new_canonical
