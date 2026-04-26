"""Аналитика price intelligence: позиция на рынке, KPI, синхронизация canonical."""

from app.analytics.canonical_sync import rebuild_canonical_from_normalized
from app.analytics.price_intelligence import (
    MarketPosition,
    compute_today_action_counts,
    load_market_rows,
    our_pricing_source,
    min_usable_for_kpi,
    position_for_canonical,
)

__all__ = [
    "MarketPosition",
    "compute_today_action_counts",
    "load_market_rows",
    "min_usable_for_kpi",
    "our_pricing_source",
    "position_for_canonical",
    "rebuild_canonical_from_normalized",
]
