"""
Прайсы Комплект-Сервис (XLS), публичные URL.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import requests
import xlrd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.compat_env import env_int
from app.collectors.normalized_io import (
    record_source_health_failure,
    replace_normalized_offers,
    upsert_source_health,
)
from app.collectors.syperopt import guess_brand_from_syperopt_name
from app.collectors.xls_common import (
    first_barcode,
    guess_vendor_code,
    iter_xls_tdm_rows,
    parse_price_ru,
    normalize_vendor_code,
)
from app.database import SourceHealth

logger = logging.getLogger(__name__)

COMPLECT_SERVICE_SOURCES: Final[dict[str, tuple[str, str]]] = {
    "ekf": ("EKF (Комплект-Сервис)", "https://www.complect-service.ru/prices/ekf.xls"),
    "iek": ("IEK (Комплект-Сервис)", "https://www.complect-service.ru/prices/ieknew.xls"),
    "schneider": (
        "Schneider Electric (КС)",
        "https://www.complect-service.ru/prices/schneider.xls",
    ),
    "legrand": ("Legrand (Комплект-Сервис)", "https://www.complect-service.ru/prices/legrand.xls"),
    "wago": ("WAGO (Комплект-Сервис)", "https://www.complect-service.ru/prices/wago.xls"),
    "full": ("Full Price (Комплект-Сервис)", "https://www.complect-service.ru/prices/fullpricecp.xls"),
}

_KEYS_NON_FULL: Final[tuple[str, ...]] = ("ekf", "iek", "schneider", "legrand", "wago")

# Порядок загрузки: отдельные бренды, затем full.
_FETCH_ORDER: Final[tuple[str, ...]] = _KEYS_NON_FULL + ("full",)

# Ключи источников для чек-листов / аудита (ожидаемые записи в source_health).
COMPLECT_SERVICE_SOURCE_KEYS: Final[tuple[str, ...]] = tuple(COMPLECT_SERVICE_SOURCES.keys())

# Для парсера XLS: фиксированный brand по ключу (full — угадывается из наименования).
_FIXED_BRAND_FOR_KEY: Final[dict[str, str | None]] = {
    "ekf": "EKF",
    "iek": "IEK",
    "schneider": "Schneider Electric",
    "legrand": "Legrand",
    "wago": "WAGO",
    "full": None,
}

# Обратная совместимость: старые имена ключей в COMPLECT_URLS.
COMPLECT_URLS: dict[str, str] = {
    "EKF": COMPLECT_SERVICE_SOURCES["ekf"][1],
    "IEK": COMPLECT_SERVICE_SOURCES["iek"][1],
    "Schneider Electric": COMPLECT_SERVICE_SOURCES["schneider"][1],
    "Legrand": COMPLECT_SERVICE_SOURCES["legrand"][1],
    "WAGO": COMPLECT_SERVICE_SOURCES["wago"][1],
    "Full": COMPLECT_SERVICE_SOURCES["full"][1],
}


def _service_timeout_connect() -> int:
    raw = os.getenv("COMPLECT_SERVICE_TIMEOUT_CONNECT")
    if raw is not None and str(raw).strip():
        return int(str(raw).strip(), 10)
    return env_int("COMPLECT_TIMEOUT_CONNECT", 20)


def _service_timeout_read() -> int:
    raw = os.getenv("COMPLECT_SERVICE_TIMEOUT_READ")
    if raw is not None and str(raw).strip():
        return int(str(raw).strip(), 10)
    return env_int("COMPLECT_TIMEOUT_READ", 300)


def _service_timeout_read_full() -> int:
    raw = os.getenv("COMPLECT_SERVICE_FULL_TIMEOUT_READ")
    if raw is not None and str(raw).strip():
        return int(str(raw).strip(), 10)
    return env_int("COMPLECT_FULL_TIMEOUT_READ", 900)


def _service_max_rows() -> int:
    raw = os.getenv("COMPLECT_SERVICE_MAX_ROWS")
    if raw is not None and str(raw).strip():
        return int(str(raw).strip(), 10)
    return env_int("COMPLECT_MAX_ROWS", 0)


def _iter_complect_simple_rows(
    sheet: Any, *, default_brand: str | None
) -> list[dict[str, Any]]:
    """
    Прайсы Комплект-Сервис: часто 3 колонки (наименование, цена, …) без строки-шапки TDM.
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


def _complect_rows_from_sheet(sheet: Any, key: str) -> list[dict[str, Any]]:
    """Сначала TDM-эвристика, иначе простой трёхколоночный формат; full — brand из наименования."""
    fixed_brand = _FIXED_BRAND_FOR_KEY.get(key)
    tdm = list(iter_xls_tdm_rows(sheet, default_brand=fixed_brand))
    if tdm:
        rows = tdm
    else:
        rows = _iter_complect_simple_rows(sheet, default_brand=fixed_brand)
    if key == "full":
        for d in rows:
            if not d.get("brand"):
                guessed = guess_brand_from_syperopt_name(str(d.get("name") or ""))
                if guessed:
                    d["brand"] = guessed
    return rows


def _complect_rows(sheet: Any, label: str) -> list[dict[str, Any]]:
    """
    Совместимость с source_audit: label — ключ ('ekf', …) или старые имена 'EKF', 'Full'.
    """
    key = _normalize_complect_label(label)
    return _complect_rows_from_sheet(sheet, key)


def _normalize_complect_label(label: str) -> str:
    """Маппинг старых подписей аудита на ключи."""
    legacy = {
        "EKF": "ekf",
        "IEK": "iek",
        "Schneider Electric": "schneider",
        "Legrand": "legrand",
        "WAGO": "wago",
        "Full": "full",
    }
    if label in legacy:
        return legacy[label]
    if label in COMPLECT_SERVICE_SOURCES:
        return label
    raise ValueError(f"Неизвестная метка Complect: {label!r}")


def _should_skip_full_price(session: Session) -> bool:
    """Не качаем fullpricecp.xls, если все пять отдельных прайсов уже успешно в source_health."""
    for k in _KEYS_NON_FULL:
        source_name, _ = COMPLECT_SERVICE_SOURCES[k]
        row = session.execute(
            select(SourceHealth).where(SourceHealth.source_name == source_name)
        ).scalar_one_or_none()
        if row is None:
            return False
        if row.last_error:
            return False
        if not row.total_rows or row.total_rows <= 0:
            return False
    logger.info(
        "Complect-Service: пропуск fullpricecp.xls — отдельные прайсы уже загружены"
    )
    return True


def fetch_complect_service_offers(session: Session, key: str = "full") -> None:
    """
    Загружает один источник Комплект-Сервис по ключу (ekf, iek, …, full).

    Args:
        session: Сессия БД.
        key: Ключ из COMPLECT_SERVICE_SOURCES.
    """
    if key not in COMPLECT_SERVICE_SOURCES:
        raise ValueError(
            f"Неизвестный ключ Complect-Service: {key!r}. "
            f"Допустимо: {', '.join(COMPLECT_SERVICE_SOURCES.keys())}"
        )
    if key == "full" and _should_skip_full_price(session):
        return

    source_name, url = COMPLECT_SERVICE_SOURCES[key]
    t_conn = _service_timeout_connect()
    t_read = _service_timeout_read_full() if key == "full" else _service_timeout_read()
    max_rows = _service_max_rows()
    t0 = time.perf_counter()

    try:
        logger.info("Complect-Service: загрузка %s (%s)", key, source_name)
        response = requests.get(
            url,
            timeout=(t_conn, t_read),
            headers={"User-Agent": "PriceDesk-Collector/1.0"},
        )
        response.raise_for_status()
        book = xlrd.open_workbook(file_contents=response.content)
        sheet = book.sheet_by_index(0)
        raw_rows = _complect_rows_from_sheet(sheet, key)
        rows: list[dict[str, Any]] = []
        for i, row in enumerate(raw_rows):
            d = dict(row)
            d["external_id"] = f"cs_{key}_{i}"
            rows.append(d)
        if max_rows > 0 and len(rows) > max_rows:
            rows = rows[:max_rows]
        replace_normalized_offers(session, source_name, url, rows, loaded_at=None)
        duration = time.perf_counter() - t0
        upsert_source_health(session, source_name, url, rows, duration_sec=duration)
        session.commit()
        logger.info("Complect-Service: сохранено %s строк (%s)", len(rows), key)
    except requests.RequestException as e:
        logger.error("Complect-Service: HTTP %s: %s", key, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"HTTP: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
    except (OSError, xlrd.XLRDError, ValueError) as e:
        logger.error("Complect-Service: файл/парсинг %s: %s", key, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"file: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
    except SQLAlchemyError as e:
        logger.error("Complect-Service: БД %s: %s", key, e)
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
        logger.error("Complect-Service: %s: %s", key, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()


def fetch_all_complect_service(session: Session) -> None:
    """
    Загружает все источники Комплект-Сервис последовательно (бренды, затем full).

    Args:
        session: Сессия БД.
    """
    for key in _FETCH_ORDER:
        fetch_complect_service_offers(session, key=key)


def fetch_complect_offers(session: Session) -> None:
    """Обратная совместимость: то же, что fetch_all_complect_service."""
    fetch_all_complect_service(session)
