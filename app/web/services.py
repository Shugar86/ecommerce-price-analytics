"""Aggregations for HTML dashboard; keeps route handlers thin."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.database import PriceAnomaly, PriceHistory, Product, ProductMatch


def build_dashboard_template_context(session: Session) -> dict[str, Any]:
    """Template context for ``dashboard.html`` (excluding ``request``)."""
    total = session.scalar(select(func.count(Product.id))) or 0
    shops = session.execute(
        select(Product.source_shop, func.count(Product.id))
        .group_by(Product.source_shop)
        .order_by(func.count(Product.id).desc())
    ).all()
    last_upd = session.scalar(select(func.max(Product.updated_at)))
    price_stats = session.execute(
        select(
            func.min(Product.price_in_rub),
            func.max(Product.price_in_rub),
            func.avg(Product.price_in_rub),
        )
    ).one()
    anomalies_n = session.scalar(select(func.count(PriceAnomaly.id))) or 0
    matches_n = session.scalar(select(func.count(ProductMatch.id))) or 0

    day_col = cast(PriceHistory.collected_at, Date)
    history_trend = session.execute(
        select(day_col, func.avg(PriceHistory.price_in_rub))
        .group_by(day_col)
        .order_by(day_col.desc())
        .limit(10)
    ).all()
    history_trend = list(reversed(history_trend))
    trend_labels = [r[0].isoformat() if r[0] else "" for r in history_trend]
    trend_values = [float(r[1] or 0) for r in history_trend]

    shop_labels = [s for s, _ in shops if s]
    shop_counts = [int(c) for s, c in shops if s]

    return {
        "total_products": int(total),
        "shops": [(s, int(c)) for s, c in shops if s],
        "last_update": last_upd,
        "price_min": float(price_stats[0] or 0),
        "price_max": float(price_stats[1] or 0),
        "price_avg": float(price_stats[2] or 0),
        "anomalies_n": int(anomalies_n),
        "matches_n": int(matches_n),
        "shop_labels_json": json.dumps(shop_labels, ensure_ascii=False),
        "shop_counts_json": json.dumps(shop_counts, ensure_ascii=False),
        "trend_labels_json": json.dumps(trend_labels, ensure_ascii=False),
        "trend_values_json": json.dumps(trend_values, ensure_ascii=False),
    }
