"""
Загрузка справочника штрихкодов (Catalog.app ZIP/CSV) в ``barcode_reference``.

Не вызывается из основного ETL без явного флага или ручного запуска.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from pathlib import Path
from typing import TextIO

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import BarcodeReference
from app.ml.matching import normalize_barcode

logger = logging.getLogger(__name__)

_DEFAULT_ZIP_URL = (
    "https://catalog.app/public-opportunities/download-public-file"
    "?fileName=barcodes_csv.zip"
)

_BATCH = 5000


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def _pick_col(row: dict[str, str], fieldmap: dict[str, str], *names: str) -> str | None:
    for name in names:
        key = _norm_header(name)
        if key in fieldmap:
            v = row.get(fieldmap[key], "")
            return str(v).strip() if v is not None else ""
    return None


def load_barcode_reference_csv(
    session: Session,
    csv_path: str | None = None,
    *,
    text_stream: TextIO | None = None,
    batch_label: str = "catalog_app",
) -> int:
    """
    Читает CSV (Catalog.app dump) и upsert-ит строки в ``barcode_reference``.

    Ожидаемые поля: id, Category, Vendor, Name, Article, Barcode (регистр гибкий).

    Args:
        session: Сессия SQLAlchemy.
        csv_path: Путь к файлу (если не задан ``text_stream``).
        text_stream: Текстовый поток CSV (взаимоисключающе с ``csv_path``).
        batch_label: Значение ``source_batch`` для партии.

    Returns:
        Число обработанных строк с валидным штрихкодом (≥ 8 цифр после нормализации).

    Raises:
        ValueError: Если не указан ни путь, ни поток.
    """
    if (csv_path is None or not str(csv_path).strip()) and text_stream is None:
        raise ValueError("Укажите csv_path или text_stream")
    bind = session.get_bind()
    use_pg = bind is not None and bind.dialect.name == "postgresql"

    def row_source() -> tuple[csv.DictReader, TextIO | None]:
        if text_stream is not None:
            return csv.DictReader(text_stream), None
        path = Path(csv_path or "")
        f = path.open(encoding="utf-8", errors="replace", newline="")
        return csv.DictReader(f), f

    reader, fh = row_source()
    try:
        if not reader.fieldnames:
            return 0
        fieldmap = {_norm_header(h): h for h in reader.fieldnames if h}
        n = 0
        batch: list[dict[str, str | None]] = []
        bbatch = batch_label[:64]

        for row in reader:
            raw_bc = _pick_col(row, fieldmap, "Barcode", "barcode", "GTIN")
            bc = normalize_barcode(raw_bc)
            if not bc or len(bc) < 8:
                continue
            article_raw = _pick_col(row, fieldmap, "Article", "article", "Артикул")
            vendor_raw = _pick_col(row, fieldmap, "Vendor", "vendor", "Производитель")
            name_raw = _pick_col(row, fieldmap, "Name", "name", "Наименование")
            category_raw = _pick_col(row, fieldmap, "Category", "category")

            article = (article_raw or "").strip() or None
            vendor = (vendor_raw or "").strip() or None
            name = (name_raw or "").strip() or None
            category = (category_raw or "").strip() or None
            art = article[:128] if article else None
            vend = vendor[:300] if vendor else None
            nam = name[:500] if name else None
            cat = category[:500] if category else None

            batch.append(
                {
                    "barcode": bc,
                    "article": art,
                    "vendor": vend,
                    "name": nam,
                    "category": cat,
                    "source_batch": bbatch,
                }
            )
            if len(batch) >= _BATCH:
                _flush_batch(session, batch, use_pg=use_pg)
                batch.clear()
                session.commit()
            n += 1
            if n % 100_000 == 0:
                logger.info("barcode_reference: обработано строк CSV: %s", n)

        if batch:
            _flush_batch(session, batch, use_pg=use_pg)
            session.commit()
        return n
    finally:
        if fh is not None:
            fh.close()


def _flush_batch(session: Session, batch: list[dict[str, str | None]], *, use_pg: bool) -> None:
    """Выполняет upsert одной пачки."""
    if not batch:
        return
    if use_pg:
        stmt = pg_insert(BarcodeReference).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[BarcodeReference.barcode],
            set_={
                "category": func.coalesce(
                    stmt.excluded.category, BarcodeReference.category
                ),
                "vendor": func.coalesce(stmt.excluded.vendor, BarcodeReference.vendor),
                "name": func.coalesce(stmt.excluded.name, BarcodeReference.name),
                "article": func.coalesce(stmt.excluded.article, BarcodeReference.article),
                "source_batch": stmt.excluded.source_batch,
            },
        )
        session.execute(stmt)
    else:
        for vals in batch:
            _sqlite_upsert_one(session, vals)


def _sqlite_upsert_one(session: Session, vals: dict[str, str | None]) -> None:
    bc = vals["barcode"]
    assert bc is not None
    ex = session.execute(
        select(BarcodeReference).where(BarcodeReference.barcode == bc)
    ).scalar_one_or_none()
    if ex is None:
        session.add(
            BarcodeReference(
                barcode=bc,
                article=vals.get("article"),
                vendor=vals.get("vendor"),
                name=vals.get("name"),
                category=vals.get("category"),
                source_batch=vals.get("source_batch"),
            )
        )
    else:
        if vals.get("article"):
            ex.article = vals["article"]
        if vals.get("vendor"):
            ex.vendor = vals["vendor"]
        if vals.get("name"):
            ex.name = vals["name"]
        if vals.get("category"):
            ex.category = vals["category"]
        if vals.get("source_batch"):
            ex.source_batch = vals["source_batch"]


def download_and_load_barcode_reference(session: Session, *, url: str | None = None) -> None:
    """
    Скачивает ZIP Catalog.app, извлекает первый CSV и загружает в БД.

    Если в таблице уже больше 100 000 строк — только лог и выход.

    Args:
        session: Сессия БД.
        url: URL архива (по умолчанию публичный Catalog.app).
    """
    cnt = session.scalar(select(func.count()).select_from(BarcodeReference))
    if cnt is not None and cnt > 100_000:
        logger.info(
            "barcode_reference: загрузка пропущена, в таблице уже %s строк",
            cnt,
        )
        return
    zip_url = url or _DEFAULT_ZIP_URL
    logger.info("barcode_reference: скачивание %s", zip_url)
    response = requests.get(
        zip_url,
        stream=True,
        timeout=120,
        headers={"User-Agent": "PriceDesk-Collector/1.0"},
    )
    response.raise_for_status()
    buf = io.BytesIO()
    for chunk in response.iter_content(chunk_size=65536):
        if chunk:
            buf.write(chunk)
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("В архиве нет CSV")
        csv_name = max(names, key=lambda n: zf.getinfo(n).file_size)
        raw = zf.read(csv_name)
    text = raw.decode("utf-8", errors="replace")
    n = load_barcode_reference_csv(
        session,
        text_stream=io.StringIO(text),
        batch_label="catalog_app_zip",
    )
    logger.info("barcode_reference: загружено строк: %s", n)
