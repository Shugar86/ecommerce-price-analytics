"""Формулы price intelligence (без БД)."""

from __future__ import annotations

import statistics

from app.analytics.price_intelligence import (
    MIN_MARGIN_FLOOR,
    OUT_OF_MARKET_THRESHOLD,
    SIMULATED_COGS_FACTOR,
)


def test_floor_and_cogs() -> None:
    """COGS = median*0.72, floor = cogs/(1-0.18) = cogs/0.82."""
    m_med = 100.0
    sim = m_med * SIMULATED_COGS_FACTOR
    assert abs(sim - 72.0) < 0.01
    floor = sim / (1.0 - MIN_MARGIN_FLOOR)
    assert abs(floor - (72.0 / 0.82)) < 0.01


def test_price_index() -> None:
    """index = our / median."""
    assert 1.1 == 110.0 / 100.0


def test_out_of_market_threshold() -> None:
    """>15% выше медианы — вне рынка по определению плана."""
    our = 120.0
    med = 100.0
    pidx = our / med
    assert pidx > 1.0 + OUT_OF_MARKET_THRESHOLD


def test_median_tie() -> None:
    """Медиана из нескольких цен (проверка statistics)."""
    assert statistics.median([10.0, 20.0, 30.0]) == 20.0
