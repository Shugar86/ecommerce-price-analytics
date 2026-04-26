"""
Локальный файл прайса (.xls) -> normalized_offers.

См. константы и смысл источника в :mod:`app.collectors.local_price_defaults`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import xlrd
from sqlalchemy.orm import Session

from app.collectors.local_price_defaults import (
    LOCAL_PRICE_DEFAULT_BRAND_FOR_ZAYAVKA,
    LOCAL_PRICE_SOURCE_NAME_DEFAULT,
    ZAYAVKA_XLS_BASENAME,
)
from app.collectors.normalized_io import (
    record_source_health_failure,
    replace_normalized_offers,
    upsert_source_health,
)
from app.collectors.xls_common import (
    first_barcode,
    guess_vendor_code,
    iter_xls_tdm_rows,
    normalize_vendor_code,
    parse_price_ru,
)

logger = logging.getLogger(__name__)


def _resolved_local_price_xls_path() -> str:
    """Путь: ``LOCAL_PRICE_XLS_PATH``, иначе ``./zayavka77rybinsk.xls`` при наличии."""
    raw = (os.getenv("LOCAL_PRICE_XLS_PATH") or "").strip()
    if raw:
        return raw
    candidate = os.path.join(os.getcwd(), ZAYAVKA_XLS_BASENAME)
    if os.path.isfile(candidate):
        logger.info(
            "LOCAL_PRICE_XLS_PATH не задан — используется %s",
            candidate,
        )
        return candidate
    return ""


def _effective_default_brand_for_path(path: str) -> str | None:
    """
    Бренд по умолчанию для строк: из env или TDM для файла zayavka (каталог ТДМ).

    Для других локальных файлов без env бренд не подставляем (не угадываем).
    """
    raw = (os.getenv("LOCAL_PRICE_DEFAULT_BRAND") or "").strip()
    if raw:
        return raw
    if os.path.basename(path).lower() == ZAYAVKA_XLS_BASENAME.lower():
        return LOCAL_PRICE_DEFAULT_BRAND_FOR_ZAYAVKA
    return None


def _simple_rows_when_no_header(
    sheet: Any, *, default_brand: str | None
) -> list[dict[str, Any]]:
    """
    Трёхколоночный формат (наименование, цена, опц. код) — как часть прайсов Complect.
    """
    rows_out: list[dict[str, Any]] = []
    nrows = getattr(sheet, "nrows", 0) or 0
    ncols = getattr(sheet, "ncols", 0) or 0
    if ncols < 2:
        return rows_out
    for r in range(nrows):
        name = str(sheet.cell_value(r, 0)).strip()
        if not name or name.lower() in ("nan", "none"):
            continue
        raw_p = sheet.cell_value(r, 1)
        if raw_p in (None, ""):
            continue
        if isinstance(raw_p, (int, float)):
            price_rub = float(raw_p)
        else:
            try:
                price_rub = parse_price_ru(str(raw_p))
            except ValueError:
                continue
        if price_rub <= 0 or price_rub > 1e7:
            continue
        v = str(sheet.cell_value(r, 2)).strip() if ncols > 2 else ""
        vendor_code = normalize_vendor_code(v) if v else guess_vendor_code(name)
        d: dict[str, Any] = {
            "name": name,
            "price_rub": price_rub,
            "vendor_code": vendor_code,
            "barcode": first_barcode(v or name),
        }
        if default_brand:
            d["brand"] = default_brand
        rows_out.append(d)
    return rows_out


def rows_from_xls_path(path: str, *, default_brand: str | None) -> list[dict[str, Any]]:
    """Парсит первый лист: TDM-подобные заголовки или простые строки."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    tdm = list(iter_xls_tdm_rows(sheet, default_brand=default_brand))
    if tdm:
        return tdm
    return _simple_rows_when_no_header(sheet, default_brand=default_brand)


def fetch_local_price_xls(session: Session) -> None:
    """
    Загружает локальный XLS при заданном пути или при наличии ``zayavka77rybinsk.xls`` в cwd.
    """
    path = _resolved_local_price_xls_path()
    if not path:
        logger.debug(
            "Локальный XLS: нет LOCAL_PRICE_XLS_PATH и нет %s в cwd — пропуск",
            ZAYAVKA_XLS_BASENAME,
        )
        return
    if not os.path.isfile(path):
        logger.warning("LOCAL_PRICE_XLS_PATH=%s: файл не найден, пропуск", path)
        return

    source_name = (
        (os.getenv("LOCAL_PRICE_SOURCE_NAME") or "").strip()
        or LOCAL_PRICE_SOURCE_NAME_DEFAULT
    )
    default_brand = _effective_default_brand_for_path(path)

    url_stub = f"file://{os.path.abspath(path)}"
    t0 = time.perf_counter()
    try:
        raw_rows = rows_from_xls_path(path, default_brand=default_brand)
        rows: list[dict[str, Any]] = []
        for i, row in enumerate(raw_rows):
            d = dict(row)
            d.setdefault("external_id", f"local_xls_{i}")
            rows.append(d)
        replace_normalized_offers(session, source_name, url_stub, rows, loaded_at=None)
        upsert_source_health(
            session,
            source_name,
            url_stub,
            rows,
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
        logger.info("Локальный XLS: сохранено %s строк (%s)", len(rows), source_name)
    except (OSError, xlrd.XLRDError, ValueError, KeyError) as e:
        logger.exception("Локальный XLS: ошибка %s", e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url_stub,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
