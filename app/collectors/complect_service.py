"""
Прайсы Комплект-Сервис (XLS), публичные URL.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
import xlrd
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.compat_env import env_int
from app.collectors.normalized_io import (
    record_source_health_failure,
    replace_normalized_offers,
    upsert_source_health,
)
from app.collectors.xls_common import (
    first_barcode,
    guess_vendor_code,
    iter_xls_tdm_rows,
    parse_price_ru,
)

logger = logging.getLogger(__name__)


def _iter_complect_simple_rows(
    sheet: Any, *, default_brand: str | None
) -> list[dict[str, Any]]:
    """
    Прайсы Комплект-Сервис: часто 3 колонки (наименование, цена, …) без строки-шапки TDM.
    """
    from app.collectors.xls_common import normalize_vendor_code

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


def _complect_rows(
    sheet: Any, label: str
) -> list[dict[str, Any]]:
    """Сначала TDM-эвристика, иначе простой трёхколоночный формат."""
    default_brand = None if label == "Full" else label
    tdm = list(iter_xls_tdm_rows(sheet, default_brand=default_brand))
    if tdm:
        return tdm
    return _iter_complect_simple_rows(sheet, default_brand=default_brand)

COMPLECT_URLS: dict[str, str] = {
    "EKF": "https://www.complect-service.ru/prices/ekf.xls",
    "IEK": "https://www.complect-service.ru/prices/ieknew.xls",
    "Schneider Electric": "https://www.complect-service.ru/prices/schneider.xls",
    "Legrand": "https://www.complect-service.ru/prices/legrand.xls",
    "WAGO": "https://www.complect-service.ru/prices/wago.xls",
    "Full": "https://www.complect-service.ru/prices/fullpricecp.xls",
}


def fetch_complect_offers(session: Session) -> None:
    """
    Скачивает каждый XLS, парсит как TDM-формат, пишет normalized_offers.

    Бренд подставляется из ключа COMPLECT_URLS (кроме Full — бренд из строки, если нет).
    """
    t_conn = env_int("COMPLECT_TIMEOUT_CONNECT", 20)
    t_read = env_int("COMPLECT_TIMEOUT_READ", 600)
    max_rows = env_int("COMPLECT_MAX_ROWS", 0)
    for label, url in COMPLECT_URLS.items():
        source_name = f"Complect {label}"
        t0 = time.perf_counter()
        try:
            logger.info("Complect: загрузка %s", label)
            response = requests.get(
                url,
                timeout=(t_conn, t_read),
                headers={"User-Agent": "PriceDesk-Collector/1.0"},
            )
            response.raise_for_status()
            book = xlrd.open_workbook(file_contents=response.content)
            sheet = book.sheet_by_index(0)
            rows: list[dict[str, Any]] = []
            rows_iter = _complect_rows(sheet, label)
            for i, row in enumerate(rows_iter):
                d = dict(row)
                d["external_id"] = f"complect_{label}_{i}"
                rows.append(d)
            if max_rows > 0 and len(rows) > max_rows:
                rows = rows[:max_rows]
            replace_normalized_offers(
                session, source_name, url, rows, loaded_at=None
            )
            duration = time.perf_counter() - t0
            upsert_source_health(
                session, source_name, url, rows, duration_sec=duration
            )
            session.commit()
            logger.info("Complect: сохранено %s строк (%s)", len(rows), label)
        except requests.RequestException as e:
            logger.error("Complect: HTTP %s: %s", label, e)
            session.rollback()
            record_source_health_failure(
                session,
                source_name,
                url,
                f"HTTP: {e}",
                duration_sec=time.perf_counter() - t0,
            )
            session.commit()
        except (xlrd.XLRDError, ValueError) as e:
            logger.error("Complect: парсинг %s: %s", label, e)
            session.rollback()
            record_source_health_failure(
                session,
                source_name,
                url,
                f"parse: {e}",
                duration_sec=time.perf_counter() - t0,
            )
            session.commit()
        except SQLAlchemyError as e:
            logger.error("Complect: БД %s: %s", label, e)
            session.rollback()
            record_source_health_failure(
                session,
                source_name,
                url,
                f"db: {e}",
                duration_sec=time.perf_counter() - t0,
            )
            session.commit()
        except Exception as e:
            logger.error("Complect: %s: %s", label, e)
            session.rollback()
            record_source_health_failure(
                session,
                source_name,
                url,
                f"{type(e).__name__}: {e}",
                duration_sec=time.perf_counter() - t0,
            )
            session.commit()
