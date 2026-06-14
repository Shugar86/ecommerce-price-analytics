"""Tests for the Open Food Facts reference connector."""

from __future__ import annotations

from app.collectors.openfoodfacts_reference import normalize_openfoodfacts_product


def test_normalize_openfoodfacts_product_success() -> None:
    """A complete product becomes a barcode reference row."""
    row = normalize_openfoodfacts_product(
        {
            "code": " 4810268031793 ",
            "product_name": "Йогурт TEOS 2%",
            "brands": "Савушкин, extra",
            "categories": "Dairies, Yogurts",
        }
    )

    assert row == {
        "barcode": "4810268031793",
        "article": None,
        "vendor": "Савушкин",
        "name": "Йогурт TEOS 2%",
        "category": "Dairies",
    }


def test_normalize_openfoodfacts_product_rejects_missing_name() -> None:
    """Rows without a useful display name are skipped."""
    row = normalize_openfoodfacts_product(
        {
            "code": "4810268031793",
            "brands": "Савушкин",
        }
    )

    assert row is None


def test_normalize_openfoodfacts_product_rejects_bad_barcode() -> None:
    """Rows without a valid barcode are skipped."""
    row = normalize_openfoodfacts_product(
        {
            "code": "abc",
            "product_name": "Йогурт TEOS 2%",
        }
    )

    assert row is None
