"""source_audit-совместимый usable_score."""

from __future__ import annotations

from app.collectors.health_stats import USABLE_WEIGHT_BARCODE, coverage_from_rows


def test_usable_score_formula() -> None:
    """Совпадает с планом: 0.5*price + 0.3*vc + 0.2*barcode (доли 0-1)."""
    rows = [
        {"price_rub": 10.0, "vendor_code": "A", "barcode": "12345678"},
    ]
    c = coverage_from_rows(rows)
    assert c.rows == 1
    # все три поля заполнены -> 100% каждое
    assert c.usable_score == 0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 1.0
    # проверяем вес штрихкода
    assert USABLE_WEIGHT_BARCODE == 0.2
