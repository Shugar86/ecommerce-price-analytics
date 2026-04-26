"""
ETL-процесс для сбора данных о ценах товаров из различных источников.

Компоненты:
- Сбор курсов валют от ЦБ РФ (XML API)
- Сбор зарубежных товаров от FakeStore API (JSON)
- Сбор российских товаров от TBM Market (YML Stream)
- Сбор прайса TDM Electric (XLS)
- Сбор каталога EKF (YML/XML)
"""

import json
import logging
import os
import signal
import time
from datetime import datetime
from io import BytesIO
import re
from typing import Any, Optional

import requests
from lxml import etree
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.analytics.canonical_sync import rebuild_canonical_from_normalized
from app.collectors.barcode_enrich import enrich_normalized_offers_from_reference
from app.collectors.barcode_reference_loader import download_and_load_barcode_reference
from app.collectors.owwa import run_owwa_ingest_stub
from app.collectors.complect_service import fetch_all_complect_service
from app.collectors.normalized_io import (
    record_source_health_failure,
    replace_normalized_offers,
    upsert_source_health,
)
from app.collectors.syperopt import fetch_syperopt_offers
from app.collectors.xls_common import iter_xls_tdm_rows
from app.database import (
    BarcodeReference,
    ExchangeRate,
    Product,
    SourceHealth,
    get_engine,
    get_session,
    init_db,
)
from app.matching.text import normalize_name_for_search
from app.price_history_util import record_price_change

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Читает int из окружения; пустая строка (часто из docker-compose) = default."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip(), 10)


def _skip_product_upsert_for_shop(source_shop: str) -> bool:
    """
    При ``SKIP_PRODUCT_UPSERT=1`` не обновляем legacy-таблицу ``products`` для фидов,
    у которых источник истины — ``normalized_offers`` (EKF, TDM). Бот/старые экраны
    по-прежнему могут читать ``products``, пока не мигрированы.
    """
    if os.getenv("SKIP_PRODUCT_UPSERT", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return False
    return source_shop in ("EKF", "TDM Electric")


def _log_etl_source_summary(session) -> None:
    """
    Сводка по source_health после цикла (лог-строка JSON для парсинга/мониторинга).
    """
    rows = list(
        session.execute(select(SourceHealth).order_by(SourceHealth.source_name)).scalars()
    )
    d = {
        r.source_name: {
            "rows": r.total_rows,
            "usable": r.usable_score,
            "error": r.last_error,
            "duration_s": r.last_fetch_duration_sec,
        }
        for r in rows
    }
    logger.info(
        "ETL_SOURCE_HEALTH_SUMMARY %s", json.dumps(d, ensure_ascii=False, default=str)
    )

# Константы для источников данных
CBR_API_URL = "http://www.cbr.ru/scripts/XML_daily.asp"
FAKESTORE_API_URL = "https://fakestoreapi.com/products"  # не используем в демо-контуре (см. ENABLE_FAKESTORE)
TBM_MARKET_YML_URL = "https://www.tbmmarket.ru/tbmmarket/service/yandex-market.xml"
GALACENTRE_YML_URL = "https://www.galacentre.ru/download/yml/yml.xml"
TDM_PRICE_XLS_URL = "https://tdme.ru/download/priceTDM.xls"
EKF_YML_URL = "https://export-xml.storage.yandexcloud.net/products.yml"

# Настройки сбора данных
# Сколько товаров грузить с каждого магазина (для очень больших фидов).
# 0 = без лимита (может быть очень долго на больших YML)
SHOP_ITEM_LIMIT = _env_int("SHOP_ITEM_LIMIT", 20000)

# Эти ключевые слова дальше используются ботом в /compare (защита от "магнитов"),
# но сборщик больше не фильтрует по ним (грузим весь каталог/лимит).
INTERSECTION_KEYWORDS = ("микроволнов", "свч", "холодиль")

UPDATE_INTERVAL = 3600  # Интервал обновления в секундах (1 час)

# Остановка по SIGTERM/SIGINT (Docker stop отправляет SIGTERM).
_shutdown_requested = False


def _request_shutdown(*_: object) -> None:
    """Помечает главный цикл для выхода после текущей итерации."""
    global _shutdown_requested
    _shutdown_requested = True

_BARCODE_RE = re.compile(r"\d{8,14}")
_VENDOR_CODE_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\\-_/\\.]{2,63}")


def _parse_price_ru(text: str) -> float:
    """Парсит цену в формате RU: '101,41' или '101.41'."""
    return float(text.strip().replace(" ", "").replace(",", "."))


def _first_barcode(raw: Optional[str]) -> Optional[str]:
    """Возвращает первый штрихкод из строки (в т.ч. 'a,b,c')."""
    if not raw:
        return None
    found = _BARCODE_RE.findall(raw)
    return found[0] if found else None


def _normalize_vendor_code(raw: Optional[str]) -> Optional[str]:
    """Нормализует артикул/код товара: trim, collapse spaces, upper."""
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    value = re.sub(r"\\s+", " ", value)
    value = value.replace(" ", "")
    return value.upper() or None


def _guess_vendor_code(raw: Optional[str]) -> Optional[str]:
    """Пытается вытащить 'похожий на артикул' токен из строки."""
    if not raw:
        return None
    m = _VENDOR_CODE_RE.search(raw)
    return _normalize_vendor_code(m.group(0)) if m else None


def _name_from_url_slug(url: Optional[str]) -> Optional[str]:
    """Строит читаемое имя из slug в URL (если явного <name> нет)."""
    if not url:
        return None
    try:
        # Берем последний сегмент пути.
        slug = url.split("?")[0].rstrip("/").split("/")[-1]
        if not slug:
            return None
        # В EKF это обычно латиницей с дефисами.
        name = slug.replace("-", " ").replace("_", " ").strip()
        name = re.sub(r"\\s+", " ", name)
        return name[:250] if name else None
    except Exception:
        return None


def _extract_param(offer_elem: etree._Element, param_name: str) -> Optional[str]:
    """Ищет <param name="...">value</param>."""
    for p in offer_elem.findall("param"):
        if p.get("name") == param_name and p.text:
            value = p.text.strip()
            return value or None
    return None


def _name_matches_intersection(name: str) -> bool:
    """Проверяет, относится ли товар к сегменту пересечения (микроволновки/холодильники)."""
    lowered = name.lower()
    return any(k in lowered for k in INTERSECTION_KEYWORDS)


def _fetch_yml_stream(url: str, *, timeout: tuple[int, int] = (10, 180)) -> requests.Response:
    """Скачивает YML/XML как stream-ответ (единый helper для всех YML источников)."""
    headers = {
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    response = requests.get(url, headers=headers, stream=True, timeout=timeout)
    response.raise_for_status()
    response.raw.decode_content = True
    return response


def _clear_parsed_offer(offer_elem: etree._Element) -> None:
    """Освобождает память после iterparse: clear + удаление соседей слева."""
    offer_elem.clear()
    while offer_elem.getprevious() is not None:
        del offer_elem.getparent()[0]


def _apply_product_upsert(
    session: Any,
    stmt: Any,
    *,
    external_id: str,
    source_shop: str,
) -> None:
    """INSERT .. ON CONFLICT для Product и запись в историю цен."""
    session.execute(stmt)
    record_price_change(session, external_id=external_id, source_shop=source_shop)


def _product_upsert_stmt_ekf(
    *,
    external_id: str,
    name: str,
    price_value: float,
    currency: str,
    price_in_rub: float,
    url: Optional[str],
    barcode: Optional[str],
    vendor_code: Optional[str],
    category_id: Optional[str],
) -> Any:
    ccy = currency if len(currency) == 3 else "RUR"
    return insert(Product).values(
        external_id=external_id,
        name=name,
        name_norm=normalize_name_for_search(name),
        price_original=price_value,
        currency=ccy,
        price_in_rub=price_in_rub,
        source_shop="EKF",
        url=url,
        barcode=barcode,
        vendor_code=vendor_code,
        category_id=category_id,
        updated_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "name": name,
            "name_norm": normalize_name_for_search(name),
            "price_original": price_value,
            "currency": ccy,
            "price_in_rub": price_in_rub,
            "url": url,
            "barcode": barcode,
            "vendor_code": vendor_code,
            "category_id": category_id,
            "updated_at": datetime.utcnow(),
        },
    )


def _product_upsert_stmt_tdm(
    *,
    external_id: str,
    name: str,
    price_rub: float,
    barcode: Optional[str],
    vendor_code: Optional[str],
) -> Any:
    return insert(Product).values(
        external_id=external_id,
        name=name,
        name_norm=normalize_name_for_search(name),
        price_original=price_rub,
        currency="RUB",
        price_in_rub=price_rub,
        source_shop="TDM Electric",
        url=None,
        barcode=barcode,
        vendor_code=vendor_code,
        category_id=None,
        updated_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "name": name,
            "name_norm": normalize_name_for_search(name),
            "price_original": price_rub,
            "price_in_rub": price_rub,
            "barcode": barcode,
            "vendor_code": vendor_code,
            "updated_at": datetime.utcnow(),
        },
    )


def _product_upsert_stmt_fakestore(
    *,
    external_id: str,
    title: str,
    price_usd: float,
    price_rub: float,
    product_id: object,
) -> Any:
    return insert(Product).values(
        external_id=external_id,
        name=title,
        name_norm=normalize_name_for_search(title),
        price_original=price_usd,
        currency="USD",
        price_in_rub=price_rub,
        source_shop="FakeStore",
        url=f"https://fakestoreapi.com/products/{product_id}",
        updated_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "name": title,
            "name_norm": normalize_name_for_search(title),
            "price_original": price_usd,
            "price_in_rub": price_rub,
            "updated_at": datetime.utcnow(),
        },
    )


def _product_upsert_stmt_tbm(
    *,
    external_id: str,
    name: str,
    price_rub: float,
    url: Optional[str],
    barcode: Optional[str],
    vendor_code: Optional[str],
    category_id: Optional[str],
) -> Any:
    return insert(Product).values(
        external_id=external_id,
        name=name,
        name_norm=normalize_name_for_search(name),
        price_original=price_rub,
        currency="RUB",
        price_in_rub=price_rub,
        source_shop="TBM Market",
        url=url,
        barcode=barcode,
        vendor_code=vendor_code,
        category_id=category_id,
        updated_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "name": name,
            "name_norm": normalize_name_for_search(name),
            "price_original": price_rub,
            "price_in_rub": price_rub,
            "barcode": barcode,
            "vendor_code": vendor_code,
            "category_id": category_id,
            "updated_at": datetime.utcnow(),
        },
    )


def _product_upsert_stmt_galacentre(
    *,
    external_id: str,
    name: str,
    price_rub: float,
    url: Optional[str],
    barcode: Optional[str],
    vendor_code: Optional[str],
    category_id: Optional[str],
) -> Any:
    return insert(Product).values(
        external_id=external_id,
        name=name,
        name_norm=normalize_name_for_search(name),
        price_original=price_rub,
        currency="RUB",
        price_in_rub=price_rub,
        source_shop="GalaCentre",
        url=url,
        barcode=barcode,
        vendor_code=vendor_code,
        category_id=category_id,
        updated_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "name": name,
            "name_norm": normalize_name_for_search(name),
            "price_original": price_rub,
            "price_in_rub": price_rub,
            "barcode": barcode,
            "vendor_code": vendor_code,
            "category_id": category_id,
            "updated_at": datetime.utcnow(),
        },
    )


def _ekf_row_from_offer(
    offer_elem: etree._Element, offer_id: str
) -> Optional[dict[str, Any]]:
    """
    Извлекает поля EKF из <offer> или None, если offer следует пропустить
    (аналог `continue` в цикле).
    """
    price_text = offer_elem.findtext("price")
    url = offer_elem.findtext("url")
    category_id = offer_elem.findtext("categoryId")
    currency = (offer_elem.findtext("currencyId") or "RUR").strip().upper()

    if not price_text:
        return None

    price_value = _parse_price_ru(price_text)

    vendor_code = (
        offer_elem.findtext("vendorCode")
        or _extract_param(offer_elem, "Артикул")
        or _extract_param(offer_elem, "Код")
        or offer_elem.findtext("model")
    )
    vendor_code = _normalize_vendor_code(vendor_code)
    barcode = _first_barcode(offer_elem.findtext("barcode"))

    name = (offer_elem.findtext("name") or "").strip()
    if not name:
        name = _name_from_url_slug(url) or vendor_code or f"EKF offer {offer_id}"

    if currency in ("RUR", "RUB"):
        price_in_rub = price_value
    else:
        price_in_rub = price_value

    return {
        "name": name,
        "price_value": price_value,
        "currency": currency,
        "price_in_rub": price_in_rub,
        "url": url,
        "barcode": barcode,
        "vendor_code": vendor_code,
        "category_id": category_id,
    }


def _tbm_row_from_offer(offer_elem: etree._Element) -> Optional[dict[str, Any]]:
    """Поля TBM Market из <offer> или None, если offer следует пропустить."""
    name_elem = offer_elem.find("name")
    price_elem = offer_elem.find("price")
    url_elem = offer_elem.find("url")

    if name_elem is None or price_elem is None:
        return None

    name = (name_elem.text or "").strip()
    price_rub = _parse_price_ru(price_elem.text)
    url = url_elem.text if url_elem is not None else None
    category_id = offer_elem.findtext("categoryId")
    barcode = _first_barcode(offer_elem.findtext("barcode"))
    vendor_code = offer_elem.findtext("vendorCode") or _extract_param(
        offer_elem, "Артикул"
    )
    return {
        "name": name,
        "price_rub": price_rub,
        "url": url,
        "barcode": barcode,
        "vendor_code": vendor_code,
        "category_id": category_id,
    }


def _galacentre_row_from_offer(offer_elem: etree._Element) -> Optional[dict[str, Any]]:
    """Поля GalaCentre из <offer> или None, если offer следует пропустить."""
    name = (offer_elem.findtext("name") or "").strip()
    price_text = offer_elem.findtext("price")
    url = offer_elem.findtext("url")
    category_id = offer_elem.findtext("categoryId")

    if not name or not price_text:
        return None

    price_rub = _parse_price_ru(price_text)
    barcode = _first_barcode(offer_elem.findtext("barcode"))
    vendor_code = _extract_param(offer_elem, "Артикул") or offer_elem.findtext("model")
    return {
        "name": name,
        "price_rub": price_rub,
        "url": url,
        "barcode": barcode,
        "vendor_code": vendor_code,
        "category_id": category_id,
    }


def _tdm_find_header_row(sheet: Any) -> tuple[Optional[int], dict[str, int]]:
    """Первая строка заголовков (первые 50 строк) и карта {lower_header: col_index}."""
    header_row_idx: Optional[int] = None
    header_map: dict[str, int] = {}
    for r in range(min(50, sheet.nrows)):
        row = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        joined = " ".join(x.lower() for x in row if x)
        if any(
            k in joined
            for k in ("артик", "наимен", "цена", "штрих", "barcode", "ean", "код")
        ):
            for c, v in enumerate(row):
                key = v.strip().lower()
                if key:
                    header_map[key] = c
            header_row_idx = r
            break
    return header_row_idx, header_map


def _tdm_map_columns(
    header_map: dict[str, int],
) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Сопоставляет стандартные поля TDM с колонками по подстрокам в заголовке."""

    def _find_col(*needles: str) -> Optional[int]:
        for k, idx in header_map.items():
            for n in needles:
                if n in k:
                    return idx
        return None

    col_name = _find_col("наимен", "товар", "номенклат", "product", "name")
    col_price = _find_col("цена", "price")
    col_vendor = _find_col("артик", "код", "sku", "vendor", "арт.")
    col_barcode = _find_col("штрих", "barcode", "ean", "gtin")
    return col_name, col_price, col_vendor, col_barcode


def _tdm_guess_barcode_column(
    sheet: Any,
    header_row_idx: int,
    col_name: int,
    col_price: int,
    col_barcode: Optional[int],
) -> Optional[int]:
    """Если колонка штрихкода не найдена по заголовку — эвристика по данным (как раньше)."""
    if col_barcode is not None:
        return col_barcode

    sample_rows = min(3000, max(0, sheet.nrows - (header_row_idx + 1)))
    best_col: Optional[int] = None
    best_hits = 0
    for c in range(sheet.ncols):
        if c in (col_name, col_price):
            continue
        hits = 0
        for r in range(
            header_row_idx + 1, min(sheet.nrows, header_row_idx + 1 + sample_rows)
        ):
            v = sheet.cell_value(r, c)
            if v in (None, ""):
                continue
            s = str(v).strip()
            if _first_barcode(s):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_col = c
    if best_col is not None and best_hits >= 50:
        logger.info(
            f"🔎 TDM: обнаружена колонка со штрихкодами по данным: col={best_col}, hits={best_hits}"
        )
        return best_col
    return col_barcode


def _tdm_try_process_xls_row(
    session: Any,
    sheet: Any,
    r: int,
    col_name: int,
    col_price: int,
    col_vendor: Optional[int],
    col_barcode: Optional[int],
) -> bool:
    """
    Парсит и upsert'ит одну строку TDM. True — если строка сохранена; False — пропуск.
    """
    name = str(sheet.cell_value(r, col_name)).strip()
    if not name or name.lower() in ("nan", "none"):
        return False

    raw_price = sheet.cell_value(r, col_price)
    if raw_price in (None, ""):
        return False

    if isinstance(raw_price, (int, float)):
        price_rub = float(raw_price)
    else:
        price_rub = _parse_price_ru(str(raw_price))

    vendor_code = None
    if col_vendor is not None:
        vendor_code = _normalize_vendor_code(str(sheet.cell_value(r, col_vendor)))
    if not vendor_code:
        vendor_code = _guess_vendor_code(name)

    barcode = None
    if col_barcode is not None:
        barcode = _first_barcode(str(sheet.cell_value(r, col_barcode)))

    external_id = f"tdm_{vendor_code or r}"
    stmt = _product_upsert_stmt_tdm(
        external_id=external_id,
        name=name,
        price_rub=price_rub,
        barcode=barcode,
        vendor_code=vendor_code,
    )
    if not _skip_product_upsert_for_shop("TDM Electric"):
        _apply_product_upsert(
            session,
            stmt,
            external_id=external_id,
            source_shop="TDM Electric",
        )
    return True


def fetch_ekf_goods(session) -> None:
    """
    Получает товары из EKF (YML/XML), фид лежит в YandexCloud.

    Загружает весь каталог (или ограничение SHOP_ITEM_LIMIT, если задано).
    """
    t_ekf0 = time.perf_counter()
    try:
        logger.info("🏭 Начинаем сбор товаров EKF (YML Stream)...")
        t_conn = _env_int("EKF_TIMEOUT_CONNECT", 10)
        t_read = _env_int("EKF_TIMEOUT_READ", 240)
        response = _fetch_yml_stream(EKF_YML_URL, timeout=(t_conn, t_read))
        saved_count = 0
        norm_rows: list[dict[str, Any]] = []

        context = etree.iterparse(
            response.raw,
            events=("end",),
            tag="offer",
            recover=True,
            huge_tree=True,
        )

        for _, offer_elem in context:
            if SHOP_ITEM_LIMIT > 0 and saved_count >= SHOP_ITEM_LIMIT:
                break

            offer_id = offer_elem.get("id")
            try:
                if not offer_id:
                    continue

                row = _ekf_row_from_offer(offer_elem, offer_id)
                if not row:
                    continue

                external_id = f"ekf_{offer_id}"
                stmt = _product_upsert_stmt_ekf(
                    external_id=external_id,
                    name=row["name"],
                    price_value=row["price_value"],
                    currency=row["currency"],
                    price_in_rub=row["price_in_rub"],
                    url=row["url"],
                    barcode=row["barcode"],
                    vendor_code=row["vendor_code"],
                    category_id=row["category_id"],
                )
                if not _skip_product_upsert_for_shop("EKF"):
                    _apply_product_upsert(
                        session, stmt, external_id=external_id, source_shop="EKF"
                    )
                saved_count += 1
                norm_rows.append(
                    {
                        "name": row["name"],
                        "price_rub": row["price_in_rub"],
                        "vendor_code": row["vendor_code"],
                        "barcode": row["barcode"],
                        "brand": "EKF",
                        "category": row.get("category_id"),
                        "url": row.get("url"),
                        "external_id": external_id,
                    }
                )

            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"⚠️ Ошибка обработки товара EKF {offer_id}: {e}")
            finally:
                _clear_parsed_offer(offer_elem)

        del context
        replace_normalized_offers(
            session, "EKF YML", EKF_YML_URL, norm_rows, loaded_at=None
        )
        upsert_source_health(
            session,
            "EKF YML",
            EKF_YML_URL,
            norm_rows,
            duration_sec=time.perf_counter() - t_ekf0,
        )
        session.commit()
        logger.info(f"✅ Успешно сохранено товаров от EKF: {saved_count}")

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к EKF: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "EKF YML",
            EKF_YML_URL,
            f"HTTP: {e}",
            duration_sec=time.perf_counter() - t_ekf0,
        )
        session.commit()
    except etree.XMLSyntaxError as e:
        logger.error(f"❌ Ошибка парсинга YML от EKF: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "EKF YML",
            EKF_YML_URL,
            f"parse: {e}",
            duration_sec=time.perf_counter() - t_ekf0,
        )
        session.commit()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении товаров EKF: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "EKF YML",
            EKF_YML_URL,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t_ekf0,
        )
        session.commit()


def fetch_tdm_goods_from_xls(session) -> None:
    """
    Получает товары TDM Electric из XLS прайс-листа.

    Важно: формат XLS зависит от поставщика; мы читаем шапку, ищем разумные колонки:
    - наименование
    - цена
    - артикул/код/sku
    - штрихкод (если есть)
    """
    try:
        import xlrd  # type: ignore
    except ModuleNotFoundError:
        logger.error("❌ Не установлен xlrd. Добавьте xlrd в requirements и пересоберите контейнер.")
        return

    t_tdm0 = time.perf_counter()
    tdm_to = _env_int("TDM_TIMEOUT_SEC", 120)
    try:
        logger.info("🏭 Начинаем сбор прайс-листа TDM (XLS)...")
        response = requests.get(TDM_PRICE_XLS_URL, timeout=tdm_to)
        response.raise_for_status()

        book = xlrd.open_workbook(file_contents=response.content)
        sheet = book.sheet_by_index(0)

        header_row_idx, header_map = _tdm_find_header_row(sheet)
        if header_row_idx is None:
            logger.error("❌ Не удалось найти строку заголовков в XLS TDM (первые 50 строк).")
            record_source_health_failure(
                session,
                "TDM Electric",
                TDM_PRICE_XLS_URL,
                "XLS: header row not found in first 50 rows",
                duration_sec=time.perf_counter() - t_tdm0,
            )
            session.commit()
            return

        col_name, col_price, col_vendor, col_barcode = _tdm_map_columns(header_map)

        if col_name is None or col_price is None:
            logger.error(
                "❌ В XLS TDM не найдены обязательные колонки name/price. "
                f"name={col_name}, price={col_price}, vendor={col_vendor}, barcode={col_barcode}"
            )
            record_source_health_failure(
                session,
                "TDM Electric",
                TDM_PRICE_XLS_URL,
                "XLS: required columns name/price not found",
                duration_sec=time.perf_counter() - t_tdm0,
            )
            session.commit()
            return

        col_barcode = _tdm_guess_barcode_column(
            sheet, header_row_idx, col_name, col_price, col_barcode
        )

        saved = 0
        for r in range(header_row_idx + 1, sheet.nrows):
            try:
                if _tdm_try_process_xls_row(
                    session,
                    sheet,
                    r,
                    col_name,
                    col_price,
                    col_vendor,
                    col_barcode,
                ):
                    saved += 1
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка обработки строки XLS TDM #{r}: {e}")

        tdm_norm: list[dict[str, Any]] = []
        for i, d in enumerate(iter_xls_tdm_rows(sheet)):
            nd = dict(d)
            nd["external_id"] = f"tdm_{i}"
            tdm_norm.append(nd)
        replace_normalized_offers(
            session, "TDM Electric", TDM_PRICE_XLS_URL, tdm_norm, loaded_at=None
        )
        upsert_source_health(
            session,
            "TDM Electric",
            TDM_PRICE_XLS_URL,
            tdm_norm,
            duration_sec=time.perf_counter() - t_tdm0,
        )
        session.commit()
        logger.info(f"✅ Успешно сохранено {saved} товаров от TDM Electric (XLS)")

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к TDM XLS: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "TDM Electric",
            TDM_PRICE_XLS_URL,
            f"HTTP: {e}",
            duration_sec=time.perf_counter() - t_tdm0,
        )
        session.commit()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при разборе XLS TDM: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "TDM Electric",
            TDM_PRICE_XLS_URL,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t_tdm0,
        )
        session.commit()


def fetch_currency(session) -> None:
    """
    Получает курсы валют от ЦБ РФ и сохраняет их в базу данных.
    
    API ЦБ РФ возвращает XML в кодировке windows-1251 с курсами всех валют.
    Функция извлекает курс USD и обновляет запись в таблице exchange_rates.
    
    Args:
        session: Сессия SQLAlchemy для работы с БД.
        
    Raises:
        requests.RequestException: При ошибке HTTP-запроса.
        etree.XMLSyntaxError: При ошибке парсинга XML.
    """
    try:
        logger.info("🌐 Начинаем сбор курсов валют от ЦБ РФ...")
        
        # HTTP запрос к API ЦБ РФ
        response = requests.get(CBR_API_URL, timeout=10)
        response.raise_for_status()
        
        # Парсинг XML с корректной кодировкой
        content = response.content
        parser = etree.XMLParser(encoding='windows-1251')
        tree = etree.parse(BytesIO(content), parser)
        root = tree.getroot()
        
        # Поиск элемента с валютой USD (CharCode = "USD")
        usd_valute = root.xpath("//Valute[CharCode='USD']")
        
        if not usd_valute:
            logger.error("❌ Не найден курс USD в ответе ЦБ РФ")
            return
        
        # Извлечение курса (Value содержит строку с запятой как разделитель)
        usd_element = usd_valute[0]
        value_text = usd_element.find('Value').text
        nominal_text = usd_element.find('Nominal').text
        
        # Конвертация: замена запятой на точку для float
        usd_rate = float(value_text.replace(',', '.'))
        nominal = int(nominal_text)
        
        # Нормализация курса (обычно nominal = 1, но бывает иначе)
        normalized_rate = usd_rate / nominal
        
        logger.info(f"💵 Получен курс USD: {normalized_rate:.4f} RUB")
        
        # UPSERT: обновление существующей записи или вставка новой
        stmt = insert(ExchangeRate).values(
            currency_code='USD',
            rate=normalized_rate,
            updated_at=datetime.utcnow()
        ).on_conflict_do_update(
            index_elements=['currency_code'],
            set_={
                'rate': normalized_rate,
                'updated_at': datetime.utcnow()
            }
        )
        
        session.execute(stmt)
        session.commit()
        
        logger.info("✅ Курс USD успешно сохранен в БД")
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к ЦБ РФ: {e}")
        session.rollback()
    except etree.XMLSyntaxError as e:
        logger.error(f"❌ Ошибка парсинга XML от ЦБ РФ: {e}")
        session.rollback()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении курсов валют: {e}")
        session.rollback()


def fetch_foreign_goods(session) -> None:
    """
    Получает информацию о зарубежных товарах от FakeStore API.
    
    FakeStore API возвращает JSON с массивом товаров в долларах США.
    Функция конвертирует цены в рубли используя курс из БД.
    
    Args:
        session: Сессия SQLAlchemy для работы с БД.
        
    Raises:
        requests.RequestException: При ошибке HTTP-запроса.
    """
    try:
        logger.info("🛒 Начинаем сбор зарубежных товаров от FakeStore API...")
        
        # Получаем актуальный курс USD из БД
        stmt = select(ExchangeRate).where(ExchangeRate.currency_code == 'USD')
        result = session.execute(stmt)
        usd_rate_obj = result.scalar_one_or_none()
        
        if not usd_rate_obj:
            logger.error("❌ Курс USD не найден в БД. Сначала запустите fetch_currency()")
            return
        
        usd_rate = usd_rate_obj.rate
        logger.info(f"💱 Используем курс USD: {usd_rate:.4f} RUB")
        
        # HTTP запрос к FakeStore API
        response = requests.get(FAKESTORE_API_URL, timeout=15)
        response.raise_for_status()
        
        products_data = response.json()
        logger.info(f"📦 Получено {len(products_data)} товаров от FakeStore")
        
        # Обработка каждого товара
        saved_count = 0
        for product_json in products_data:
            try:
                product_id = product_json.get('id')
                title = product_json.get('title', 'Unknown Product')
                price_usd = float(product_json.get('price', 0))
                
                # Конвертация цены в рубли
                price_rub = price_usd * usd_rate
                
                # Формирование уникального external_id
                external_id = f"fakestore_{product_id}"
                stmt = _product_upsert_stmt_fakestore(
                    external_id=external_id,
                    title=title,
                    price_usd=price_usd,
                    price_rub=price_rub,
                    product_id=product_id,
                )
                _apply_product_upsert(
                    session,
                    stmt,
                    external_id=external_id,
                    source_shop="FakeStore",
                )
                saved_count += 1
                
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка обработки товара {product_json}: {e}")
                continue
        
        session.commit()
        logger.info(f"✅ Успешно сохранено {saved_count} товаров от FakeStore")
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к FakeStore API: {e}")
        session.rollback()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении зарубежных товаров: {e}")
        session.rollback()


def fetch_russian_goods(session) -> None:
    """
    Получает информацию о российских товарах от TBM Market (YML формат).
    
    Использует потоковый парсинг (streaming) для обработки больших XML-файлов
    без полной загрузки в память.     Обрабатывает первые N товаров из фида.
    Дублирует срез в ``normalized_offers`` / ``source_health`` (``TBM Market``), как EKF YML.
    
    Args:
        session: Сессия SQLAlchemy для работы с БД.
        
    Raises:
        requests.RequestException: При ошибке HTTP-запроса.
        etree.XMLSyntaxError: При ошибке парсинга YML.
    """
    t0 = time.perf_counter()
    try:
        logger.info("🏪 Начинаем сбор российских товаров от TBM Market (YML Stream)...")
        
        # HTTP запрос с потоковой передачей данных
        response = requests.get(TBM_MARKET_YML_URL, stream=True, timeout=(10, 60))
        response.raise_for_status()
        response.raw.decode_content = True
        
        logger.info("📡 Начинаем потоковый парсинг YML...")
        
        # Потоковый парсинг XML через iterparse (memory-efficient)
        saved_count = 0
        norm_rows: list[dict[str, Any]] = []
        context = etree.iterparse(
            response.raw,
            events=('end',),
            tag='offer'
        )
        
        for event, offer_elem in context:
            if SHOP_ITEM_LIMIT > 0 and saved_count >= SHOP_ITEM_LIMIT:
                break
            
            try:
                # Извлечение атрибутов и элементов товара
                offer_id = offer_elem.get('id')
                
                if not offer_id:
                    continue

                row = _tbm_row_from_offer(offer_elem)
                if not row:
                    continue
                
                # Формирование уникального external_id
                external_id = f"tbm_{offer_id}"
                stmt = _product_upsert_stmt_tbm(
                    external_id=external_id,
                    name=row["name"],
                    price_rub=row["price_rub"],
                    url=row["url"],
                    barcode=row["barcode"],
                    vendor_code=row["vendor_code"],
                    category_id=row["category_id"],
                )
                _apply_product_upsert(
                    session,
                    stmt,
                    external_id=external_id,
                    source_shop="TBM Market",
                )
                norm_rows.append(
                    {
                        "name": row["name"],
                        "price_rub": row["price_rub"],
                        "vendor_code": row.get("vendor_code"),
                        "barcode": row.get("barcode"),
                        "category": row.get("category_id"),
                        "url": row.get("url"),
                        "external_id": external_id,
                    }
                )
                saved_count += 1

                # Очистка элемента из памяти (важно для streaming)
                _clear_parsed_offer(offer_elem)
                
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"⚠️ Ошибка обработки товара {offer_id}: {e}")
                continue
        
        # Очистка контекста парсера
        del context
        replace_normalized_offers(
            session, "TBM Market", TBM_MARKET_YML_URL, norm_rows, loaded_at=None
        )
        upsert_source_health(
            session,
            "TBM Market",
            TBM_MARKET_YML_URL,
            norm_rows,
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
        logger.info(f"✅ Успешно сохранено товаров от TBM Market: {saved_count}")
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к TBM Market: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "TBM Market",
            TBM_MARKET_YML_URL,
            f"HTTP: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
    except etree.XMLSyntaxError as e:
        logger.error(f"❌ Ошибка парсинга YML от TBM Market: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "TBM Market",
            TBM_MARKET_YML_URL,
            f"parse: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении российских товаров: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "TBM Market",
            TBM_MARKET_YML_URL,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t0,
        )
        session.commit()


def fetch_galacentre_goods(session) -> None:
    """
    Получает товары из Гала-Центра (YML), без API-ключа.

    Загружает весь каталог (или ограничение SHOP_ITEM_LIMIT, если задано).
    Дублирует срез в ``normalized_offers`` / ``source_health`` (``GalaCentre``), как TBM/EKF.
    """
    t_outer = time.perf_counter()
    try:
        logger.info("🏪 Начинаем сбор российских товаров от GalaCentre (YML Stream)...")

        headers = {
            # Reduce chance of broken chunked responses and huge gzip buffers.
            "Accept-Encoding": "identity",
            "Connection": "close",
        }

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            saved_count = 0
            pending_writes = 0
            norm_rows: list[dict[str, Any]] = []

            try:
                t_gala0 = time.perf_counter()
                response = requests.get(
                    GALACENTRE_YML_URL,
                    headers=headers,
                    stream=True,
                    timeout=(10, 180),
                )
                response.raise_for_status()
                response.raw.decode_content = True

                context = etree.iterparse(
                    response.raw,
                    events=("end",),
                    tag="offer",
                    recover=True,
                    huge_tree=True,
                )

                for _, offer_elem in context:
                    if SHOP_ITEM_LIMIT > 0 and saved_count >= SHOP_ITEM_LIMIT:
                        break

                    offer_id = offer_elem.get("id")
                    try:
                        if not offer_id:
                            continue

                        row = _galacentre_row_from_offer(offer_elem)
                        if not row:
                            continue

                        external_id = f"galacentre_{offer_id}"
                        stmt = _product_upsert_stmt_galacentre(
                            external_id=external_id,
                            name=row["name"],
                            price_rub=row["price_rub"],
                            url=row["url"],
                            barcode=row["barcode"],
                            vendor_code=row["vendor_code"],
                            category_id=row["category_id"],
                        )
                        _apply_product_upsert(
                            session,
                            stmt,
                            external_id=external_id,
                            source_shop="GalaCentre",
                        )
                        norm_rows.append(
                            {
                                "name": row["name"],
                                "price_rub": row["price_rub"],
                                "vendor_code": row.get("vendor_code"),
                                "barcode": row.get("barcode"),
                                "category": row.get("category_id"),
                                "url": row.get("url"),
                                "external_id": external_id,
                            }
                        )
                        pending_writes += 1
                        saved_count += 1

                        # Commit in small batches so partial results survive transient network failures.
                        if pending_writes >= 25:
                            session.commit()
                            pending_writes = 0

                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"⚠️ Ошибка обработки товара GalaCentre {offer_id}: {e}")
                    finally:
                        _clear_parsed_offer(offer_elem)

                del context
                if pending_writes:
                    session.commit()
                replace_normalized_offers(
                    session, "GalaCentre", GALACENTRE_YML_URL, norm_rows, loaded_at=None
                )
                upsert_source_health(
                    session,
                    "GalaCentre",
                    GALACENTRE_YML_URL,
                    norm_rows,
                    duration_sec=time.perf_counter() - t_gala0,
                )
                session.commit()

                logger.info(
                    f"✅ Успешно сохранено товаров от GalaCentre: {saved_count}"
                )
                break

            except (requests.RequestException, etree.XMLSyntaxError) as e:
                # Keep whatever was committed, but do not keep an open transaction.
                try:
                    session.rollback()
                except Exception:
                    pass

                if attempt < max_attempts:
                    logger.warning(
                        f"⚠️ Ошибка загрузки/парсинга GalaCentre (попытка {attempt}/{max_attempts}): {e}. Повтор..."
                    )
                    continue

                logger.error(f"❌ Не удалось загрузить GalaCentre после {max_attempts} попыток: {e}")
                record_source_health_failure(
                    session,
                    "GalaCentre",
                    GALACENTRE_YML_URL,
                    f"after {max_attempts} attempts: {e}",
                    duration_sec=time.perf_counter() - t_gala0,
                )
                session.commit()
                break

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка при запросе к GalaCentre: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "GalaCentre",
            GALACENTRE_YML_URL,
            f"HTTP: {e}",
            duration_sec=time.perf_counter() - t_outer,
        )
        session.commit()
    except etree.XMLSyntaxError as e:
        logger.error(f"❌ Ошибка парсинга YML от GalaCentre: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "GalaCentre",
            GALACENTRE_YML_URL,
            f"parse: {e}",
            duration_sec=time.perf_counter() - t_outer,
        )
        session.commit()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении товаров GalaCentre: {e}")
        session.rollback()
        record_source_health_failure(
            session,
            "GalaCentre",
            GALACENTRE_YML_URL,
            f"{type(e).__name__}: {e}",
            duration_sec=time.perf_counter() - t_outer,
        )
        session.commit()


def collect_all_data(session) -> None:
    """
    Выполняет полный цикл сбора данных из всех источников.
    
    Последовательность:
    1. Получение курсов валют (необходимо для конвертации)
    2. Получение зарубежных товаров
    3. Получение российских товаров
    
    Args:
        session: Сессия SQLAlchemy для работы с БД.
    """
    logger.info("=" * 60)
    logger.info("🚀 Запуск цикла сбора данных")
    logger.info("=" * 60)
    
    # Шаг 1: Курсы валют (критически важно для следующих шагов)
    fetch_currency(session)

    # Шаг 2: FakeStore — только по ENABLE_FAKESTORE=1 (не в демо-контуре)
    if os.getenv("ENABLE_FAKESTORE", "").strip().lower() in ("1", "true", "yes"):
        fetch_foreign_goods(session)
    else:
        logger.info("⏭️ FakeStore пропущен (включите ENABLE_FAKESTORE=1 при необходимости)")

    # Шаг 3: Российские товары (TBM)
    fetch_russian_goods(session)

    # Шаг 4: Российские товары (GalaCentre)
    fetch_galacentre_goods(session)

    # Шаг 5: Товары EKF (YML)
    fetch_ekf_goods(session)

    # Шаг 6: TDM Electric (XLS)
    fetch_tdm_goods_from_xls(session)

    # Шаг 7–8: Complect-Service (XLS), Syperopt (XLSX) -> normalized_offers
    fetch_all_complect_service(session)
    # Syperopt: в pipeline; URL http://www.syperopt.ru/...xlsx проверен (200 OK, XLSX).
    fetch_syperopt_offers(session)

    # Обогащение из barcode_reference (если таблица заполнена) и канонизация
    try:
        enrich_normalized_offers_from_reference(session)
    except (SQLAlchemyError, ValueError, OSError) as e:
        logger.warning("barcode enrich: %s", e)
    try:
        run_owwa_ingest_stub(session)
    except (SQLAlchemyError, ValueError, OSError) as e:
        logger.warning("owwa ingest: %s", e)
        session.rollback()
    try:
        rebuild_canonical_from_normalized(session)
    except (SQLAlchemyError, ValueError, OSError) as e:
        logger.error("canonical sync: %s", e)
    try:
        _log_etl_source_summary(session)
    except (SQLAlchemyError, TypeError) as e:
        logger.warning("ETL source summary: %s", e)

    logger.info("=" * 60)
    logger.info("✅ Цикл сбора данных завершен")
    logger.info("=" * 60)


def main() -> None:
    """
    Главная функция процесса-сборщика данных.
    
    Инициализирует БД и запускает бесконечный цикл сбора данных
    с периодическими обновлениями согласно UPDATE_INTERVAL.
    """
    logger.info("🎯 Инициализация сборщика данных...")
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    try:
        # Создание подключения к БД
        engine = get_engine()
        logger.info("✅ Подключение к БД установлено")
        
        # Инициализация структуры БД
        init_db(engine)

        if os.getenv("BARCODE_REFERENCE_AUTO_LOAD", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            _session = get_session(engine)
            try:
                n_ref = _session.scalar(select(func.count()).select_from(BarcodeReference))
                if n_ref == 0:
                    logger.info(
                        "BARCODE_REFERENCE_AUTO_LOAD: загрузка справочника штрихкодов"
                    )
                    download_and_load_barcode_reference(_session)
                    _session.commit()
            except (SQLAlchemyError, OSError, ValueError) as e:
                logger.warning("BARCODE_REFERENCE_AUTO_LOAD: %s", e)
                _session.rollback()
            finally:
                _session.close()

        # Бесконечный цикл сбора данных
        while not _shutdown_requested:
            try:
                # Создаем новую сессию для каждого цикла
                session = get_session(engine)
                
                try:
                    collect_all_data(session)
                finally:
                    session.close()
                
                if _shutdown_requested:
                    logger.info("⏹️ Завершение по сигналу после цикла сбора.")
                    break

                # Ожидание перед следующим циклом
                logger.info(f"⏰ Следующий сбор данных через {UPDATE_INTERVAL} секунд...")
                time.sleep(UPDATE_INTERVAL)
                
            except SQLAlchemyError as e:
                logger.error(f"❌ Ошибка БД в цикле сбора: {e}")
                time.sleep(60)  # Короткая пауза перед повтором при ошибке БД
            except KeyboardInterrupt:
                logger.info("⏹️ Получен сигнал остановки. Завершение работы...")
                break
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка в главном цикле: {e}")
                time.sleep(60)  # Короткая пауза перед повтором
    
    except Exception as e:
        logger.critical(f"💀 Критическая ошибка при инициализации: {e}")
        raise


if __name__ == "__main__":
    main()

