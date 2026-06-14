"""
Прайс-листы CARRETA.RU (CSV, CP1251, разделитель ``;``).

Демонстрационный региональный источник (РФ): автозапчасти, объёмный каталог.
"""

from __future__ import annotations

import csv
import logging
import os
import time
from io import StringIO
from typing import Any

import requests
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.compat_env import env_int
from app.collectors.normalized_io import (
    record_source_health_failure,
    replace_normalized_offers,
    upsert_source_health,
)

logger = logging.getLogger(__name__)

CARRETA_PRICE_PAGE = "https://carreta.ru/prices-and-api/"

CARRETA_FEEDS: tuple[tuple[str, str], ...] = (
    (
        "carreta_nsk_opt",
        "https://carreta.ru/media/carreta_pricelist_52jv.csv",
    ),
    (
        "carreta_nsk_retail",
        "https://carreta.ru/media/carreta_pricelist_9onq.csv",
    ),
    (
        "carreta_nsk_stock",
        "https://carreta.ru/media/carreta_pricelist_80m3.csv",
    ),
)


def _norm_header(key: str) -> str:
    """Убирает BOM и лишние пробелы у имени столбца."""
    return key.replace("\ufeff", "").strip()


def _parse_availability_bool(
    raw_in_stock: str | None,
    *_rest: str | None,
) -> bool | None:
    """Переводит поле «В наличии» в bool для колонки ``normalized_offers.availability``.

    Остальные поля сроков в CSV не сохраняются: в схеме БД только boolean, без текста.
    """
    if raw_in_stock is None:
        return None
    s = str(raw_in_stock).strip().lower().replace(",", ".")
    if not s:
        return None
    try:
        v = float(s)
        if v > 0:
            return True
        if v == 0:
            return False
    except ValueError:
        pass
    if s in ("да", "yes", "true", "есть", "+"):
        return True
    if s in ("нет", "no", "false", "-"):
        return False
    return None


def parse_carreta_csv_text(
    text: str,
    *,
    max_rows: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Парсит текст CSV CARRETA в офферы ``normalized_offers``.

    Args:
        text: Содержимое файла в Unicode (уже декодировано из cp1251).
        max_rows: Лимит валидных строк; ``0`` = без лимита.

    Returns:
        Кортеж (список словарей для ``replace_normalized_offers``, число пропущенных
        строк из-за ошибок парсинга цены или пустого имени).
    """
    skipped = 0
    out: list[dict[str, Any]] = []
    reader = csv.DictReader(StringIO(text), delimiter=";")
    for i, raw in enumerate(reader, start=1):
        if max_rows > 0 and len(out) >= max_rows:
            break
        if not raw:
            skipped += 1
            continue
        row = {_norm_header(k): (v.strip() if isinstance(v, str) else "") for k, v in raw.items()}
        name = row.get("Наименование") or ""
        if not name or len(name) < 3:
            skipped += 1
            continue
        price_raw = row.get("Цена") or ""
        if not price_raw:
            skipped += 1
            continue
        try:
            price_rub = float(price_raw.replace(" ", "").replace(",", "."))
        except ValueError:
            skipped += 1
            continue
        if price_rub <= 0:
            skipped += 1
            continue
        vendor = (row.get("Код") or "").strip() or None
        brand = (row.get("Производитель") or "").strip() or None
        availability = _parse_availability_bool(
            row.get("В наличии"),
            row.get("Заказ от"),
            row.get("Срок мин"),
            row.get("Срок макс"),
        )
        external_id = f"carreta_{vendor or 'nocode'}_{i}"
        out.append(
            {
                "name": name[:500],
                "price_rub": price_rub,
                "vendor_code": vendor[:128] if vendor else None,
                "brand": brand[:200] if brand else None,
                "barcode": None,
                "category": None,
                "url": CARRETA_PRICE_PAGE,
                "external_id": external_id[:255],
                "availability": availability,
            }
        )
    return out, skipped


def parse_carreta_csv_bytes(
    content: bytes,
    *,
    max_rows: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Декодирует CP1251 и вызывает :func:`parse_carreta_csv_text`."""
    text = content.decode("cp1251", errors="replace")
    return parse_carreta_csv_text(text, max_rows=max_rows)


def _fetch_one_feed(
    session: Session,
    source_name: str,
    url: str,
    *,
    max_rows: int,
    t_conn: int,
    t_read: int,
) -> None:
    t0 = time.perf_counter()
    try:
        logger.info("CARRETA: загрузка %s", source_name)
        response = requests.get(
            url,
            timeout=(t_conn, t_read),
            headers={"User-Agent": "PriceDesk-Collector/1.0"},
        )
        response.raise_for_status()
        rows, skipped = parse_carreta_csv_bytes(response.content, max_rows=max_rows)
        replace_normalized_offers(session, source_name, url, rows, loaded_at=None)
        duration = time.perf_counter() - t0
        upsert_source_health(
            session,
            source_name,
            url,
            rows,
            duration_sec=duration,
        )
        logger.info(
            "CARRETA: %s — %s строк, пропусков парсера %s, %.2f c",
            source_name,
            len(rows),
            skipped,
            duration,
        )
        session.commit()
    except requests.RequestException as e:
        duration = time.perf_counter() - t0
        logger.warning("CARRETA: %s — HTTP %s", source_name, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"http: {type(e).__name__}: {e}",
            duration_sec=duration,
        )
        session.commit()
    except (OSError, UnicodeDecodeError, ValueError) as e:
        duration = time.perf_counter() - t0
        logger.warning("CARRETA: %s — parse %s", source_name, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"parse: {type(e).__name__}: {e}",
            duration_sec=duration,
        )
        session.commit()
    except SQLAlchemyError as e:
        duration = time.perf_counter() - t0
        logger.warning("CARRETA: %s — БД %s", source_name, e)
        session.rollback()
        record_source_health_failure(
            session,
            source_name,
            url,
            f"db: {type(e).__name__}: {e}",
            duration_sec=duration,
        )
        session.commit()


def fetch_carreta_offers(session: Session) -> None:
    """Скачивает три прайса CARRETA Новосибирск и пишет в ``normalized_offers``.

    Управление:
        ``ENABLE_CARRETA`` — ``1``/``true``/``yes`` для включения.
        ``CARRETA_MAX_ROWS`` — лимит строк на **каждый** файл (``0`` = без лимита).
        ``CARRETA_TIMEOUT_CONNECT`` / ``CARRETA_TIMEOUT_READ`` — таймауты HTTP.
    """
    if os.getenv("ENABLE_CARRETA", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        logger.info(
            "⏭️ CARRETA пропущен (включите ENABLE_CARRETA=1 для демо REGION CSV)"
        )
        return

    max_rows = env_int("CARRETA_MAX_ROWS", 20_000)
    t_conn = env_int("CARRETA_TIMEOUT_CONNECT", 30)
    t_read = env_int("CARRETA_TIMEOUT_READ", 900)
    for source_name, url in CARRETA_FEEDS:
        _fetch_one_feed(
            session,
            source_name,
            url,
            max_rows=max_rows,
            t_conn=t_conn,
            t_read=t_read,
        )