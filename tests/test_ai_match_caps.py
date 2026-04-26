"""Лимиты fuzzy-кандидатов на пару источников (ai_worker)."""

from __future__ import annotations

import pytest

from app import ai_worker


def test_offer_cap_per_pair_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MATCH_OFFER_CAP_PER_PAIR", "77")
    assert ai_worker._offer_cap_per_pair(9) == 77


def test_offer_cap_per_pair_splits_total(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MATCH_OFFER_CAP_PER_PAIR", raising=False)
    monkeypatch.setattr(ai_worker, "AI_MATCH_OFFER_CAP", 400)
    # 9 пар -> floor 400/9 = 44
    assert ai_worker._offer_cap_per_pair(9) == 44


def test_offer_cap_per_pair_minimum_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MATCH_OFFER_CAP_PER_PAIR", raising=False)
    monkeypatch.setattr(ai_worker, "AI_MATCH_OFFER_CAP", 5)
    assert ai_worker._offer_cap_per_pair(100) == 1
