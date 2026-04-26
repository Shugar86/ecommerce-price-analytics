"""Тесты приоритета matching (exact раньше fuzzy)."""

from __future__ import annotations

import pytest

from app.ml.matching import (
    is_fuzzy_for_review_only,
    match_pair,
    norm_vendor_code,
    normalize_barcode,
)


def test_barcode_beats_titles() -> None:
    """Одинаковый штрихкод даёт exact_barcode даже при разных названиях."""
    a = {"barcode": "4606050300105", "name": "A", "brand": "X", "vendor_code": "1"}
    b = {"barcode": "460 6050 300105", "name": "B", "brand": "Y", "vendor_code": "2"}
    r = match_pair(a, b)
    assert r is not None
    assert r.kind == "exact_barcode"
    assert r.is_automated is True
    assert r.confidence == 1.0


def test_vendor_brand_pair() -> None:
    """Артикул + бренд без штрихкода — приоритет над текстом."""
    a = {
        "barcode": None,
        "name": "Клеммник",
        "brand": "WAGO",
        "vendor_code": "221-412",
        "category": "Клеммы",
    }
    b = {
        "barcode": None,
        "name": "Другое имя",
        "brand": "WAGO",
        "vendor_code": "221-412",
        "category": "Акс",
    }
    r = match_pair(a, b)
    assert r is not None
    assert r.kind == "exact_vendor_brand"
    assert r.is_automated is True


def test_fuzzy_is_not_automated() -> None:
    """Fuzzy only для ревью."""
    assert is_fuzzy_for_review_only("fuzzy_tfidf") is True
    a = {
        "barcode": None,
        "name": "Автомат однополюсный 10А C",
        "brand": None,
        "vendor_code": None,
        "category": None,
    }
    b = {
        "barcode": None,
        "name": "Автомат 10A C однополюс",
        "brand": None,
        "vendor_code": None,
        "category": None,
    }
    r = match_pair(a, b)
    if r is not None and r.kind == "fuzzy_tfidf":
        assert r.is_automated is False


def test_empty_returns_none() -> None:
    """Пустые сущности — нет пары."""
    assert match_pair({}, {}) is None


def test_norm_vendor() -> None:
    """Пробелы в артикуле схлопываются."""
    assert norm_vendor_code("  ab-cd  ") == "AB-CD"
    assert normalize_barcode(" 123 456 7890 12 ") == "123456789012"
