"""Тесты нормализации наименований перед эвристиками сходства."""

from __future__ import annotations

from app.ml.name_normalization import normalize_title_for_matching


def test_yo_spacing_and_units() -> None:
    """Ё→е, схлопывание пробелов, единицы → qty."""
    s = normalize_title_for_matching("  Прибор ёмкий  Шт. ")
    assert "ё" not in s
    assert "  " not in s
    assert "qty" in s


def test_brand_tokens_normalized() -> None:
    """Токены распространённых брендов в нижнем регистре/canonical slug."""
    s = normalize_title_for_matching("Клемма WAGO 221 IEK тип")
    assert "wago" in s.split()
    assert "iek" in s.split()


def test_name_only_improves_with_normalization_pipeline() -> None:
    """Score не падает при применении нормализации перед ``name_only_score``."""
    from app.matching.text import name_only_score

    a_raw = "ABB  Выключатель-automatic 16A "
    b_raw = "abb автоматический выключатель   16a"
    na = normalize_title_for_matching(a_raw)
    nb = normalize_title_for_matching(b_raw)
    before = float(name_only_score(a_raw.lower(), b_raw.lower()))
    after = float(name_only_score(na, nb))
    assert after >= before
