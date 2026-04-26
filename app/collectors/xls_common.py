"""
Общие функции для прайсов в формате XLS (TDM/Complect): поиск заголовков и строк.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_BARCODE_RE = re.compile(r"\d{8,14}")
_VENDOR_CODE_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\\-_/\\.]{2,63}")


def parse_price_ru(text: str) -> float:
    """Парсит цену в формате RU: '101,41' или '101.41'."""
    return float(text.strip().replace(" ", "").replace(",", "."))


def first_barcode(raw: Optional[str]) -> Optional[str]:
    """Возвращает первый штрихкод из строки (в т.ч. 'a,b,c')."""
    if not raw:
        return None
    found = _BARCODE_RE.findall(raw)
    return found[0] if found else None


def normalize_vendor_code(raw: Optional[str]) -> Optional[str]:
    """Нормализует артикул/код товара: trim, collapse spaces, upper."""
    if not raw:
        return None
    value = str(raw).strip()
    if not value or value.lower() in ("nan", "none"):
        return None
    value = re.sub(r"\s+", " ", value)
    value = value.replace(" ", "")
    return value.upper() or None


def guess_vendor_code(raw: Optional[str]) -> Optional[str]:
    """Пытается вытащить 'похожий на артикул' токен из строки."""
    if not raw:
        return None
    m = _VENDOR_CODE_RE.search(str(raw))
    return normalize_vendor_code(m.group(0)) if m else None


def tdm_find_header_row(sheet: Any) -> tuple[Optional[int], dict[str, int]]:
    """Первая строка заголовков (первые 50 строк) и карта {lower_header: col_index}."""
    header_row_idx: Optional[int] = None
    header_map: dict[str, int] = {}
    nrows = getattr(sheet, "nrows", 0) or 0
    ncols = getattr(sheet, "ncols", 0) or 0
    for r in range(min(50, nrows)):
        row = [str(sheet.cell_value(r, c)).strip() for c in range(ncols)]
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


def tdm_map_columns(
    header_map: dict[str, int],
) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Сопоставляет стандартные поля TDM с колонками по подстрокам в заголовке."""

    def _find_col(*needles: str) -> Optional[int]:
        for k, idx in header_map.items():
            for n in needles:
                if n in k:
                    return idx
        return None

    col_name = _find_col("наимен", "назван", "товар", "номенклат", "product", "name")
    col_price = _find_col("цена", "price")
    col_vendor = _find_col("артик", "код", "sku", "vendor", "арт.")
    col_barcode = _find_col("штрих", "barcode", "ean", "gtin")
    return col_name, col_price, col_vendor, col_barcode


def tdm_guess_barcode_column(
    sheet: Any,
    header_row_idx: int,
    col_name: int,
    col_price: int,
    col_barcode: Optional[int],
) -> Optional[int]:
    """Если колонка штрихкода не найдена — эвристика по данным."""
    if col_barcode is not None:
        return col_barcode

    nrows = getattr(sheet, "nrows", 0) or 0
    ncols = getattr(sheet, "ncols", 0) or 0
    sample_rows = min(3000, max(0, nrows - (header_row_idx + 1)))
    best_col: Optional[int] = None
    best_hits = 0
    for c in range(ncols):
        if c in (col_name, col_price):
            continue
        hits = 0
        for r in range(
            header_row_idx + 1, min(nrows, header_row_idx + 1 + sample_rows)
        ):
            v = sheet.cell_value(r, c)
            if v in (None, ""):
                continue
            s = str(v).strip()
            if first_barcode(s):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_col = c
    if best_col is not None and best_hits >= 50:
        logger.info("XLS: колонка штрихкодов по данным: col=%s hits=%s", best_col, best_hits)
        return best_col
    return col_barcode


def iter_xls_tdm_rows(
    sheet: Any,
    *,
    default_brand: Optional[str] = None,
) -> Iterator[dict[str, Any]]:
    """
    Итерирует строки прайса в TDM-подобном формате.

    Yields:
        Словарь: name, price_rub, vendor_code, barcode, brand (если задан).
    """
    header_row_idx, header_map = tdm_find_header_row(sheet)
    if header_row_idx is None or not header_map:
        return

    col_name, col_price, col_vendor, col_barcode = tdm_map_columns(header_map)
    if col_name is None or col_price is None:
        return

    col_barcode = tdm_guess_barcode_column(
        sheet, header_row_idx, col_name, col_price, col_barcode
    )
    nrows = getattr(sheet, "nrows", 0) or 0

    for r in range(header_row_idx + 1, nrows):
        name = str(sheet.cell_value(r, col_name)).strip()
        if not name or name.lower() in ("nan", "none"):
            continue
        raw_price = sheet.cell_value(r, col_price)
        if raw_price in (None, ""):
            continue
        if isinstance(raw_price, (int, float)):
            price_rub = float(raw_price)
        else:
            try:
                price_rub = parse_price_ru(str(raw_price))
            except ValueError:
                continue

        vendor_code = None
        if col_vendor is not None:
            vendor_code = normalize_vendor_code(str(sheet.cell_value(r, col_vendor)))
        if not vendor_code:
            vendor_code = guess_vendor_code(name)

        barcode = None
        if col_barcode is not None:
            barcode = first_barcode(str(sheet.cell_value(r, col_barcode)))

        row: dict[str, Any] = {
            "name": name,
            "price_rub": price_rub,
            "vendor_code": vendor_code,
            "barcode": barcode,
        }
        if default_brand:
            row["brand"] = default_brand
        yield row
