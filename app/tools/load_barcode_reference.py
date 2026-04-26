"""
Загрузка CSV справочника штрихкодов в barcode_reference.

Ожидаемые колонки (регистр заголовков гибкий): Barcode, Article, Vendor, Name, Category.

Запуск: ``BARCODE_REFERENCE_CSV=/path/to/file.csv python -m app.tools.load_barcode_reference``

Пакет Catalog.app: распаковать CSV и указать путь; сеть в рантайме не обязательна.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import BarcodeReference, get_engine, get_session, init_db
from app.ml.matching import normalize_barcode

logger = logging.getLogger(__name__)


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def _upsert_row_sqlite(
    session,
    *,
    barcode: str,
    article: str | None,
    vendor: str | None,
    name: str | None,
    category: str | None,
    batch: str,
) -> None:
    """Insert or update одной строки (SQLite и прочие движки)."""
    ex = session.execute(
        select(BarcodeReference).where(BarcodeReference.barcode == barcode)
    ).scalar_one_or_none()
    if ex is None:
        session.add(
            BarcodeReference(
                barcode=barcode,
                article=article,
                vendor=vendor,
                name=name,
                category=category,
                source_batch=batch[:64],
            )
        )
    else:
        ex.article = article
        ex.vendor = vendor
        ex.name = name
        ex.category = category
        ex.source_batch = batch[:64]


def load_csv(session, path: Path, *, batch: str) -> int:
    """
    Читает CSV и upsert-ит строки в barcode_reference.

    Args:
        session: Сессия SQLAlchemy.
        path: Путь к CSV.
        batch: Метка загрузки (source_batch).

    Returns:
        Число обработанных строк с валидным штрихкодом.
    """
    bind = session.get_bind()
    use_pg_upsert = bind.dialect.name == "postgresql"
    n = 0
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0
        fieldmap = {_norm_header(h): h for h in reader.fieldnames}

        def col(row: dict[str, str], *names: str) -> str | None:
            for name in names:
                key = _norm_header(name)
                if key in fieldmap:
                    return row.get(fieldmap[key], "")  # type: ignore[arg-type]
            return None

        for row in reader:
            raw_bc = col(row, "Barcode", "barcode", "GTIN")
            bc = normalize_barcode(raw_bc)
            if not bc:
                continue
            article = (col(row, "Article", "article", "Артикул") or "").strip() or None
            vendor = (col(row, "Vendor", "vendor", "Производитель") or "").strip() or None
            name = (col(row, "Name", "name", "Наименование") or "").strip() or None
            category = (col(row, "Category", "category") or "").strip() or None
            art = article[:128] if article else None
            vend = vendor[:300] if vendor else None
            nam = name[:500] if name else None
            cat = category[:500] if category else None
            bbatch = batch[:64]
            if use_pg_upsert:
                stmt = pg_insert(BarcodeReference).values(
                    barcode=bc,
                    article=art,
                    vendor=vend,
                    name=nam,
                    category=cat,
                    source_batch=bbatch,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[BarcodeReference.barcode.key],
                    set_={
                        "article": stmt.excluded.article,
                        "vendor": stmt.excluded.vendor,
                        "name": stmt.excluded.name,
                        "category": stmt.excluded.category,
                        "source_batch": stmt.excluded.source_batch,
                    },
                )
                session.execute(stmt)
            else:
                _upsert_row_sqlite(
                    session,
                    barcode=bc,
                    article=art,
                    vendor=vend,
                    name=nam,
                    category=cat,
                    batch=bbatch,
                )
            n += 1
            if n % 5000 == 0:
                session.commit()
                logger.info("Загружено строк: %s", n)
    session.commit()
    return n


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description="Load barcode_reference from CSV")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=os.environ.get("BARCODE_REFERENCE_CSV", ""),
        help="Path to CSV (or set BARCODE_REFERENCE_CSV)",
    )
    parser.add_argument(
        "--batch",
        default=os.environ.get("BARCODE_REFERENCE_BATCH", "import"),
        help="source_batch label",
    )
    args = parser.parse_args()
    if not args.csv_path:
        print("Укажите путь к CSV или BARCODE_REFERENCE_CSV", file=sys.stderr)
        sys.exit(2)
    path = Path(args.csv_path)
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        sys.exit(2)
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        n = load_csv(session, path, batch=str(args.batch))
        print(f"Loaded {n} barcode rows", file=sys.stderr)
    except Exception as exc:
        logger.exception("Ошибка загрузки: %s", exc)
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
