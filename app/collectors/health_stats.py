"""
Метрики покрытия и usable_score (как в source_audit / source_health).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

USABLE_WEIGHT_PRICE = 0.5
USABLE_WEIGHT_VENDOR = 0.3
USABLE_WEIGHT_BARCODE = 0.2


@dataclass(frozen=True)
class CoverageResult:
    """Статистика по полям в наборе строк-офферов."""

    rows: int
    price_pct: float
    vendor_code_pct: float
    barcode_pct: float
    brand_pct: float
    usable_score: float


def _pct(n: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return 100.0 * n / total


def row_has_price(r: Mapping[str, Any]) -> bool:
    """Строка считается имеющей цену, если price_rub положителен."""
    p = r.get("price_rub")
    return p is not None and float(p) > 0


def row_has_str(r: Mapping[str, Any], key: str) -> bool:
    v = r.get(key)
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and s.lower() not in ("nan", "none")


def coverage_from_rows(rows: Sequence[Mapping[str, Any]]) -> CoverageResult:
    """
    Считает доли полей и usable_score.

    Args:
        rows: Словари с опциональными ключами price_rub, vendor_code, barcode, brand.

    Returns:
        CoverageResult; при rows=0 — нули и usable 0.
    """
    total = len(rows)
    if total == 0:
        return CoverageResult(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n_price = sum(1 for r in rows if row_has_price(r))
    n_vc = sum(1 for r in rows if row_has_str(r, "vendor_code"))
    n_bc = sum(1 for r in rows if row_has_str(r, "barcode"))
    n_br = sum(1 for r in rows if row_has_str(r, "brand"))

    price_pct = _pct(n_price, total)
    vendor_pct = _pct(n_vc, total)
    barcode_pct = _pct(n_bc, total)
    brand_pct = _pct(n_br, total)

    usable = (
        USABLE_WEIGHT_PRICE * price_pct / 100.0
        + USABLE_WEIGHT_VENDOR * vendor_pct / 100.0
        + USABLE_WEIGHT_BARCODE * barcode_pct / 100.0
    )
    return CoverageResult(
        rows=total,
        price_pct=round(price_pct, 2),
        vendor_code_pct=round(vendor_pct, 2),
        barcode_pct=round(barcode_pct, 2),
        brand_pct=round(brand_pct, 2),
        usable_score=round(usable, 4),
    )
