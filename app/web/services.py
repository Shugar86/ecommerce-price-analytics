"""Aggregations for HTML dashboard; keeps route handlers thin."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.database import (
    MATCH_KIND_FUZZY_TFIDF,
    MATCH_STATUS_CONFIRMED,
    MATCH_STATUS_REJECTED,
    MATCH_STATUS_SUGGESTED,
    NormalizedOfferMatch,
    PriceAnomaly,
    PriceHistory,
    Product,
    ProductMatch,
)
from app.analytics.price_intelligence import (
    TodayActionStats,
    compute_today_action_counts,
    our_pricing_source,
)
from app.database import SourceHealth
from app.quality.coverage import build_quality_dashboard_slice
from sqlalchemy import select as sa_select


def list_source_health_rows(session: Session) -> list[SourceHealth]:
    """Все записи source_health для /sources (реестр)."""
    return list(
        session.execute(
            sa_select(SourceHealth).order_by(SourceHealth.source_name.asc())
        ).scalars().all()
    )


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
    matches_suggested_n = int(
        (
            session.scalar(
                select(func.count(NormalizedOfferMatch.id)).where(
                    NormalizedOfferMatch.match_kind == MATCH_KIND_FUZZY_TFIDF,
                    NormalizedOfferMatch.match_status == MATCH_STATUS_SUGGESTED,
                )
            )
            or 0
        )
        + (
            session.scalar(
                select(func.count(ProductMatch.id)).where(
                    ProductMatch.match_kind == MATCH_KIND_FUZZY_TFIDF,
                    ProductMatch.match_status == MATCH_STATUS_SUGGESTED,
                )
            )
            or 0
        )
    )
    matches_confirmed_n = (
        session.scalar(
            select(func.count(ProductMatch.id)).where(
                ProductMatch.match_status == MATCH_STATUS_CONFIRMED
            )
        )
        or 0
    )
    matches_rejected_n = (
        session.scalar(
            select(func.count(ProductMatch.id)).where(
                ProductMatch.match_status == MATCH_STATUS_REJECTED
            )
        )
        or 0
    )

    quality = build_quality_dashboard_slice(session)
    shop_completeness = quality.get("shop_completeness", [])

    # Sources where neither barcode nor vendor_code is substantially filled.
    weak_sources = [
        r for r in shop_completeness
        if r.total > 10 and r.pct(r.with_barcode) < 15 and r.pct(r.with_vendor_code) < 15
    ]

    attention_items: list[dict[str, Any]] = []
    if anomalies_n >= 10:
        attention_items.append({
            "level": "danger",
            "label": f"Обнаружено {anomalies_n} аномалий цен",
            "link": "/alerts",
            "link_text": "Посмотреть",
        })
    elif anomalies_n > 0:
        attention_items.append({
            "level": "warning",
            "label": f"Обнаружено {anomalies_n} аномалий цен",
            "link": "/alerts",
            "link_text": "Посмотреть",
        })
    if matches_suggested_n > 0:
        attention_items.append({
            "level": "info",
            "label": f"{matches_suggested_n} кандидатов на сопоставление ожидают ревью аналитика",
            "link": "/matches",
            "link_text": "Перейти",
        })
    if weak_sources:
        names = ", ".join(r.source_shop for r in weak_sources[:3])
        attention_items.append({
            "level": "muted",
            "label": f"Источники без надёжных идентификаторов (нет штрихкодов/артикулов): {names}",
            "link": None,
            "link_text": None,
        })

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

    today: TodayActionStats = compute_today_action_counts(
        session, our_src=our_pricing_source()
    )

    return {
        "total_products": int(total),
        "shops": [(s, int(c)) for s, c in shops if s],
        "shops_n": len([s for s, _ in shops if s]),
        "last_update": last_upd,
        "price_min": float(price_stats[0] or 0),
        "price_max": float(price_stats[1] or 0),
        "price_avg": float(price_stats[2] or 0),
        "anomalies_n": int(anomalies_n),
        "matches_suggested_n": int(matches_suggested_n),
        "matches_confirmed_n": int(matches_confirmed_n),
        "matches_rejected_n": int(matches_rejected_n),
        "attention_items": attention_items,
        "shop_labels_json": json.dumps(shop_labels, ensure_ascii=False),
        "shop_counts_json": json.dumps(shop_counts, ensure_ascii=False),
        "trend_labels_json": json.dumps(trend_labels, ensure_ascii=False),
        "trend_values_json": json.dumps(trend_values, ensure_ascii=False),
        "our_pricing_source": our_pricing_source(),
        "today": today,
        **quality,
    }
