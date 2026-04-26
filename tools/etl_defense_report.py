#!/usr/bin/env python3
"""
Срез БД и URL веб-интерфейса для слайдов защиты (ETL, норм. слой, fuzzy-матчи).

Запуск с хоста (venv, опубликованный PostgreSQL в dev-compose)::

    .venv/bin/python tools/etl_defense_report.py

Запуск внутри контейнера (тот же образ, что web/collector)::

    docker compose exec web python tools/etl_defense_report.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import (
    CanonicalProduct,
    NormalizedOffer,
    NormalizedOfferMatch,
    SourceHealth,
    get_engine,
    get_session,
)

logger = logging.getLogger(__name__)


def _resolve_web_base_url() -> str:
    """Собирает базовый URL веб-интерфейса для ссылок в отчёте.

    Returns:
        Строка вида ``http://host:port`` без завершающего слэша.
    """
    direct = os.getenv("DEFENSE_REPORT_BASE_URL") or os.getenv("WEB_BASE_URL")
    if direct:
        return direct.rstrip("/")
    host = os.getenv("WEB_HOST", "localhost")
    port = os.getenv("WEB_PORT", "8000")
    return f"http://{host}:{port}"


@dataclass(frozen=True, slots=True)
class OfferCountRow:
    """Одна строка агрегата ``normalized_offers`` по ``source_name``."""

    source_name: str
    count: int


@dataclass(frozen=True, slots=True)
class MatchCountRow:
    """Одна строка агрегата ``normalized_offer_matches`` по ``match_status``."""

    match_status: str
    count: int


def _format_dt(value: Optional[datetime]) -> str:
    """Возвращает ISO-представление времени или «—»."""
    if value is None:
        return "—"
    return value.isoformat(sep=" ", timespec="seconds")


def _query_offer_counts_by_source(session: Session) -> list[OfferCountRow]:
    """Считает ``COUNT(*)`` по ``normalized_offers`` сгруппировано по ``source_name``."""
    rows = session.execute(
        select(NormalizedOffer.source_name, func.count().label("n"))
        .group_by(NormalizedOffer.source_name)
        .order_by(NormalizedOffer.source_name)
    ).all()
    return [OfferCountRow(str(r[0]), int(r[1])) for r in rows]


def _query_match_counts_by_status(session: Session) -> list[MatchCountRow]:
    """Считает ``COUNT(*)`` по ``normalized_offer_matches`` по ``match_status``."""
    rows = session.execute(
        select(NormalizedOfferMatch.match_status, func.count().label("n"))
        .group_by(NormalizedOfferMatch.match_status)
        .order_by(NormalizedOfferMatch.match_status)
    ).all()
    return [MatchCountRow(str(r[0]), int(r[1])) for r in rows]


def _query_source_health_max_times(session: Session) -> dict[str, Optional[datetime]]:
    """Возвращает ``max(updated_at)`` и ``max(last_loaded_at)`` по ``source_health``."""
    u = session.execute(select(func.max(SourceHealth.updated_at))).scalar_one()
    l = session.execute(select(func.max(SourceHealth.last_loaded_at))).scalar_one()
    return {"max_source_health_updated_at": u, "max_source_last_loaded_at": l}


def _count_canonical_total(session: Session) -> int:
    """Количество записей в ``canonical_products``."""
    return int(session.execute(select(func.count()).select_from(CanonicalProduct)).scalar_one() or 0)


def _count_offers_with_canonical(session: Session) -> int:
    """Офферы с непустым ``canonical_product_id``."""
    return int(
        session.execute(
            select(func.count())
            .select_from(NormalizedOffer)
            .where(NormalizedOffer.canonical_product_id.isnot(None))
        ).scalar_one()
        or 0
    )


def _count_canonical_with_two_plus_sources(session: Session) -> int:
    """Канонические карточки, у которых ≥2 разных ``source_name`` в ``normalized_offers``."""
    sql = text(
        """
        SELECT COUNT(*) FROM (
            SELECT canonical_product_id
            FROM normalized_offers
            WHERE canonical_product_id IS NOT NULL
            GROUP BY canonical_product_id
            HAVING COUNT(DISTINCT source_name) >= 2
        ) t
        """
    )
    return int(session.execute(sql).scalar_one() or 0)


def _load_source_health_rows(session: Session) -> list[SourceHealth]:
    """Все строки ``source_health`` (срез для защиты)."""
    return list(
        session.execute(select(SourceHealth).order_by(SourceHealth.source_name)).scalars().all()
    )


def _source_health_to_dict(row: SourceHealth) -> dict[str, Any]:
    """Сериализация одной строки ``source_health`` для JSON-блока в отчёте."""
    return {
        "source_name": row.source_name,
        "last_loaded_at": _format_dt(row.last_loaded_at),
        "total_rows": row.total_rows,
        "last_error": row.last_error,
        "last_fetch_duration_sec": row.last_fetch_duration_sec,
        "updated_at": _format_dt(row.updated_at),
    }


def build_report_lines(session: Session) -> list[str]:
    """Формирует текстовые строки отчёта (UTF-8)."""
    base = _resolve_web_base_url()
    times = _query_source_health_max_times(session)
    offer_rows = _query_offer_counts_by_source(session)
    match_rows = _query_match_counts_by_status(session)
    n_canonical = _count_canonical_total(session)
    n_offers_canon = _count_offers_with_canonical(session)
    n_canon_2src = _count_canonical_with_two_plus_sources(session)
    sh_rows = _load_source_health_rows(session)

    lines: list[str] = [
        "=== ETL / defense report ===",
        f"DB snapshot: {_format_dt(datetime.now(timezone.utc))} UTC (script run time)",
        "",
        "Freshness (from source_health; no separate log of ETL_SOURCE_HEALTH_SUMMARY in DB):",
        f"  max(updated_at)          : {_format_dt(times['max_source_health_updated_at'])}",
        f"  max(last_loaded_at)     : {_format_dt(times['max_source_last_loaded_at'])}",
        "",
        f"normalized_offers total rows: {sum(r.count for r in offer_rows)}",
        "normalized_offers by source_name:",
    ]
    for r in offer_rows:
        lines.append(f"  {r.source_name!r}: {r.count}")
    if not offer_rows:
        lines.append("  (no rows)")

    lines += [
        "",
        f"canonical_products rows              : {n_canonical}",
        f"normalized_offers with canonical_id  : {n_offers_canon}",
        f"canonical clusters with 2+ sources  : {n_canon_2src}",
        "",
        "normalized_offer_matches by match_status:",
    ]
    for r in match_rows:
        lines.append(f"  {r.match_status!r}: {r.count}")
    if not match_rows:
        lines.append("  (no rows)")

    lines += [
        "",
        "Web UI base URL (set WEB_HOST/WEB_PORT or DEFENSE_REPORT_BASE_URL):",
        f"  {base}",
        "Screenshot paths:",
        f"  {base}/",
        f"  {base}/sources",
        f"  {base}/market",
        f"  {base}/matches",
        f"  {base}/alerts",
        "",
        "source_health JSON (all rows):",
    ]
    payload = [_source_health_to_dict(r) for r in sh_rows]
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    return lines


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Парсит аргументы CLI."""
    p = argparse.ArgumentParser(
        description="Срез БД после ETL для цифр в слайды защиты."
    )
    p.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Опционально записать тот же вывод в файл (UTF-8).",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Не логировать в stderr (только stdout/файл).",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа: печать отчёта в stdout и опционально в файл.

    Returns:
        0 при успехе, 1 при ошибке подключения к БД.
    """
    args = _parse_args(argv)
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        engine = get_engine()
    except ValueError as exc:
        logger.error("Не удалось собрать URL БД: %s", exc)
        return 1
    session = get_session(engine)
    try:
        lines = build_report_lines(session)
        text_out = "\n".join(lines) + "\n"
        sys.stdout.write(text_out)
        if args.out is not None:
            try:
                args.out.write_text(text_out, encoding="utf-8")
            except OSError as exc:
                logger.error("Не удалось записать %s: %s", args.out, exc)
                return 1
    except SQLAlchemyError as exc:
        logger.error("Ошибка при чтении БД: %s", exc, exc_info=True)
        return 1
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
