"""
Запись нормализованных офферов в БД и обновление source_health.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.collectors.health_stats import coverage_from_rows
from app.database import NormalizedOffer, SourceHealth

logger = logging.getLogger(__name__)


def replace_normalized_offers(
    session: Session,
    source_name: str,
    source_url: str | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    loaded_at: datetime | None = None,
) -> int:
    """
    Удаляет предыдущие офферы источника и вставляет новый набор.

    Args:
        session: Сессия БД.
        source_name: Уникальное имя источника (как в SourceHealth).
        source_url: URL фида.
        rows: Словари с полями name, price_rub, vendor_code, barcode, brand, category,
            url, external_id, availability.
        loaded_at: Метка времени загрузки (по умолчанию UTC now).

    Returns:
        Число вставленных строк.
    """
    t = loaded_at or datetime.utcnow()
    session.execute(
        delete(NormalizedOffer).where(NormalizedOffer.source_name == source_name)
    )
    n = 0
    for r in rows:
        session.add(
            NormalizedOffer(
                source_name=source_name,
                source_url=source_url,
                external_id=(str(r.get("external_id")) if r.get("external_id") else None),
                name=(str(r.get("name"))[:500] if r.get("name") else None),
                brand=(str(r.get("brand"))[:200] if r.get("brand") else None),
                vendor_code=(str(r.get("vendor_code"))[:128] if r.get("vendor_code") else None),
                barcode=(str(r.get("barcode"))[:128] if r.get("barcode") else None),
                category=(str(r.get("category"))[:200] if r.get("category") else None),
                price_rub=float(r["price_rub"])
                if r.get("price_rub") is not None
                else None,
                availability=r.get("availability"),
                url=(str(r.get("url"))[:1000] if r.get("url") else None),
                loaded_at=t,
            )
        )
        n += 1
    return n


def upsert_source_health(
    session: Session,
    source_name: str,
    source_url: str | None,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """
    Обновляет или создаёт запись source_health по покрытию rows.

    Args:
        session: Сессия БД.
        source_name: Имя источника.
        source_url: URL.
        rows: Те же данные, что ушли в replace_normalized_offers.
    """
    cov = coverage_from_rows(list(rows))
    row = session.execute(
        select(SourceHealth).where(SourceHealth.source_name == source_name)
    ).scalar_one_or_none()
    if row is None:
        row = SourceHealth(
            source_name=source_name,
            source_url=source_url,
        )
        session.add(row)

    row.last_loaded_at = datetime.utcnow()
    row.source_url = source_url
    row.total_rows = cov.rows
    row.price_pct = cov.price_pct
    row.vendor_code_pct = cov.vendor_code_pct
    row.barcode_pct = cov.barcode_pct
    row.brand_pct = cov.brand_pct
    row.usable_score = cov.usable_score
    row.updated_at = datetime.utcnow()
    logger.info(
        "source_health %s: rows=%s usable=%.3f",
        source_name,
        cov.rows,
        cov.usable_score or 0.0,
    )
