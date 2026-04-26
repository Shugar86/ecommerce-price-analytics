"""Парсинг AI_MATCH_SOURCE_PAIRS и prior OUR_PRICING_SOURCE."""

from __future__ import annotations

import pytest

from app.analytics.price_intelligence import our_pricing_source
from app.matching.source_pairs import (
    default_normalized_match_pairs,
    local_price_source_name,
    parse_ai_match_source_pairs,
)


def test_parse_pairs_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Список пар из AI_MATCH_SOURCE_PAIRS."""
    monkeypatch.setenv("AI_MATCH_SOURCE_PAIRS", "A|B;C|D")
    monkeypatch.delenv("AI_MATCH_NORMALIZED_LEFT", raising=False)
    monkeypatch.delenv("AI_MATCH_NORMALIZED_RIGHT", raising=False)
    assert parse_ai_match_source_pairs() == [("A", "B"), ("C", "D")]


def test_malformed_pairs_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Кривой AI_MATCH_SOURCE_PAIRS → расширенный дефолт."""
    monkeypatch.setenv("AI_MATCH_SOURCE_PAIRS", ";;;|")
    monkeypatch.delenv("AI_MATCH_SINGLE_PAIR_FALLBACK", raising=False)
    pairs = parse_ai_match_source_pairs()
    assert ("TDM Electric", "IEK (Комплект-Сервис)") in pairs


def test_single_pair_fallback_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_MATCH_SINGLE_PAIR_FALLBACK=1 — одна пара LEFT/RIGHT (легаси)."""
    monkeypatch.delenv("AI_MATCH_SOURCE_PAIRS", raising=False)
    monkeypatch.setenv("AI_MATCH_SINGLE_PAIR_FALLBACK", "1")
    monkeypatch.setenv("AI_MATCH_NORMALIZED_LEFT", "X")
    monkeypatch.setenv("AI_MATCH_NORMALIZED_RIGHT", "Y")
    assert parse_ai_match_source_pairs() == [("X", "Y")]


def test_default_multi_pairs_include_iek_and_ekf_yml_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без env — расширенный дефолт: IEK раньше, EKF YML в конце."""
    monkeypatch.delenv("AI_MATCH_SOURCE_PAIRS", raising=False)
    monkeypatch.delenv("AI_MATCH_SINGLE_PAIR_FALLBACK", raising=False)
    monkeypatch.delenv("LOCAL_PRICE_SOURCE_NAME", raising=False)
    pairs = parse_ai_match_source_pairs()
    assert ("TDM Electric", "IEK (Комплект-Сервис)") in pairs
    assert pairs[-1] == ("EKF YML", "TDM Electric")


def test_local_price_name_in_default_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOCAL_PRICE_SOURCE_NAME попадает в пару с TDM (локальный файл — тот же бренд, что федеральный TDM)."""
    monkeypatch.delenv("AI_MATCH_SOURCE_PAIRS", raising=False)
    monkeypatch.delenv("AI_MATCH_SINGLE_PAIR_FALLBACK", raising=False)
    monkeypatch.setenv("LOCAL_PRICE_SOURCE_NAME", "Custom Local")
    pairs = default_normalized_match_pairs()
    assert ("TDM Electric", "Custom Local") in pairs
    assert ("IEK (Комплект-Сервис)", "Custom Local") not in pairs
    assert local_price_source_name() == "Custom Local"


def test_our_pricing_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OUR_PRICING_SOURCE имеет приоритет над priority list."""
    monkeypatch.setenv("OUR_PRICING_SOURCE", "Single")
    monkeypatch.setenv("OUR_PRICING_SOURCE_PRIORITY", "A,B")
    assert our_pricing_source() == "Single"


def test_our_pricing_from_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Первый из priority при пустом OUR_PRICING_SOURCE."""
    monkeypatch.delenv("OUR_PRICING_SOURCE", raising=False)
    monkeypatch.setenv("OUR_PRICING_SOURCE_PRIORITY", "  First  ,  Second  ")
    assert our_pricing_source() == "First"


def test_our_pricing_default_ekf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без env — дефолт EKF YML (обратная совместимость)."""
    monkeypatch.delenv("OUR_PRICING_SOURCE", raising=False)
    monkeypatch.delenv("OUR_PRICING_SOURCE_PRIORITY", raising=False)
    assert our_pricing_source() == "EKF YML"
