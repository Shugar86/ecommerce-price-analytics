"""
Экспорт зафиксированного демо-снимка из БД в ``artifacts/demo``.

Используется для воспроизводимых слайдов ВКР: ``manifest.json`` + ``offers.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors.carreta import CARRETA_FEEDS
from app.database import (
    NormalizedOffer,
    SourceHealth,
    get_database_url,
    get_engine,
    get_session,
    init_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _mask_db_url(raw: str) -> str:
    """Маскирует пароль в DSN для логов/манифеста."""
    if "@" not in raw or "://" not in raw:
        return raw
    try:
        head, tail = raw.split("://", 1)
        creds, host = tail.rsplit("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{head}://{user}:****@{host}"
    except ValueError:
        pass
    return raw


def _default_sources() -> list[str]:
    raw = (os.getenv("DEFENSE_SNAPSHOT_SOURCES") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [name for name, _ in CARRETA_FEEDS]


def export_snapshot(
    out_dir: Path,
    *,
    per_source_limit: int,
) -> dict[str, Any]:
    """Выгружает CSV и manifest; возвращает manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    sources = _default_sources()
    counts: dict[str, int] = {}
    loaded_rows: list[NormalizedOffer] = []
    try:
        for sn in sources:
            n_proj = session.scalar(
                select(func.count()).select_from(NormalizedOffer).where(
                    NormalizedOffer.source_name == sn
                )
            )
            counts[sn] = int(n_proj or 0)
            chunk = session.scalars(
                select(NormalizedOffer)
                .where(NormalizedOffer.source_name == sn)
                .order_by(NormalizedOffer.id)
                .limit(per_source_limit)
            ).all()
            loaded_rows.extend(chunk)

        csv_path = out_dir / "offers.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "id",
                    "source_name",
                    "name",
                    "brand",
                    "vendor_code",
                    "barcode",
                    "price_rub",
                    "loaded_at",
                ]
            )
            for r in loaded_rows:
                w.writerow(
                    [
                        r.id,
                        r.source_name,
                        r.name or "",
                        r.brand or "",
                        r.vendor_code or "",
                        r.barcode or "",
                        r.price_rub if r.price_rub is not None else "",
                        r.loaded_at.isoformat() if r.loaded_at else "",
                    ]
                )

        health_rows = session.execute(
            select(SourceHealth).where(SourceHealth.source_name.in_(sources))
        ).scalars()
        health_json = [
            {
                "source_name": h.source_name,
                "source_url": h.source_url,
                "total_rows": h.total_rows,
                "last_error": h.last_error,
                "last_fetch_duration_sec": h.last_fetch_duration_sec,
            }
            for h in health_rows
        ]

        # Воронка (оценки по факту экспорта)
        funnel_stages = [
            {"name": "Экспорт офферов (строки)", "value": len(loaded_rows)},
        ]
        by_sn: dict[str, list[NormalizedOffer]] = {}
        for r in loaded_rows:
            by_sn.setdefault(r.source_name or "", []).append(r)
        opt_codes = {
            str(x.vendor_code).strip().upper()
            for x in by_sn.get(CARRETA_FEEDS[0][0], [])
            if x.vendor_code
        }
        ret_codes = {
            str(x.vendor_code).strip().upper()
            for x in by_sn.get(CARRETA_FEEDS[1][0], [])
            if x.vendor_code
        }
        joined = len(opt_codes & ret_codes)
        funnel_stages.append(
            {"name": "Коды в обоих CARRETA (опт∩розница)", "value": joined}
        )

        manifest: dict[str, Any] = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "database_url_masked": _mask_db_url(get_database_url()),
            "sources_requested": sources,
            "per_source_counts_db": counts,
            "per_source_limit_export": per_source_limit,
            "exported_offer_rows": len(loaded_rows),
            "carreta_vendor_code_overlap_opt_retail": joined,
            "source_health_snapshot": health_json,
            "thresholds": {
                "FUZZY_NAME_JACCARD_MIN": os.getenv("FUZZY_NAME_JACCARD_MIN", ""),
            },
            "funnel": {"stages": funnel_stages},
            "notes": (
                "Снимок для демонстрации ВКР. CARRETA — открытые CSV; Open Food Facts "
                "не является источником цен."
            ),
        }
        manifest_path = out_dir / "manifest.json"
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info("Записано %s строк в %s", len(loaded_rows), csv_path)
        return manifest
    finally:
        session.close()


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/demo"),
        help="Каталог для manifest.json и offers.csv",
    )
    parser.add_argument(
        "--per-source-limit",
        type=int,
        default=12_000,
        help="Максимум строк на источник в CSV",
    )
    args = parser.parse_args()
    export_snapshot(args.out_dir, per_source_limit=args.per_source_limit)


if __name__ == "__main__":
    main()
