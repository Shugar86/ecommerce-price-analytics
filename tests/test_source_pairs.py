"""Парсинг AI_MATCH_SOURCE_PAIRS и prior OUR_PRICING_SOURCE."""

from __future__ import annotations

import os

import pytest

from app.analytics.price_intelligence import our_pricing_source
from app.matching.source_pairs import parse_ai_match_source_pairs


def test_parse_pairs_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Список пар из AI_MATCH_SOURCE_PAIRS."""
    monkeypatch.setenv("AI_MATCH_SOURCE_PAIRS", "A|B;C|D")
    monkeypatch.delenv("AI_MATCH_NORMALIZED_LEFT", raising=False)
    monkeypatch.delenv("AI_MATCH_NORMALIZED_RIGHT", raising=False)
    assert parse_ai_match_source_pairs() == [("A", "B"), ("C", "D")]


def test_parse_pairs_fallback_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без AI_MATCH_SOURCE_PAIRS — пары с LEFT/RIGHT."""
    monkeypatch.delenv("AI_MATCH_SOURCE_PAIRS", raising=False)
    monkeypatch.setenv("AI_MATCH_NORMALIZED_LEFT", "X")
    monkeypatch.setenv("AI_MATCH_NORMALIZED_RIGHT", "Y")
    assert parse_ai_match_source_pairs() == [("X", "Y")]


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
