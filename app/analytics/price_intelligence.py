"""
KPI price intelligence: индекс цены, маржа к условной COGS, рекомендуемое действие.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import (
    MATCH_KIND_FUZZY_TFIDF,
    MATCH_STATUS_SUGGESTED,
    CanonicalProduct,
    NormalizedOffer,
    ProductMatch,
    SourceHealth,
)

SIMULATED_COGS_FACTOR = 0.72
MIN_MARGIN_FLOOR = 0.18
OUT_OF_MARKET_THRESHOLD = 0.15
MIN_USABLE_FOR_KPI = 0.6


@dataclass(frozen=True)
class MarketPosition:
    """Позиция товара относительно 'рынка' (агрегат конкурирующих офферов)."""

    canonical_id: int
    status: str
    market_min: float | None
    market_median: float | None
    market_max: float | None
    our_price: float | None
    price_index: float | None
    margin_pct: float | None
    floor_price: float | None
    simulated_cogs: float | None
    recommended_action: str
    competitors_count: int


def our_pricing_source() -> str:
    """Источник, который считаем 'нашим' для сравнения (env или EKF)."""
    v = (os.getenv("OUR_PRICING_SOURCE") or "").strip()
    return v or "EKF YML"


def min_usable_for_kpi() -> float:
    """Минимальный usable_score источника для участия в рыночном KPI."""
    raw = (os.getenv("KPI_USABLE_FLOOR") or str(MIN_USABLE_FOR_KPI)).strip()
    try:
        return float(raw)
    except ValueError:
        return MIN_USABLE_FOR_KPI


def _source_usable(
    session: Session, source_name: str | None
) -> float | None:
    if not source_name:
        return None
    sh = session.execute(
        select(SourceHealth).where(SourceHealth.source_name == source_name)
    ).scalar_one_or_none()
    if sh is None or sh.usable_score is None:
        return None
    return float(sh.usable_score)


def _is_usable_for_kpi(
    session: Session, source_name: str | None, floor: float
) -> bool:
    u = _source_usable(session, source_name)
    if u is None:
        return True
    return u >= floor


def _prices_for_canonical(
    session: Session, canonical_id: int, kpi_floor: float
) -> list[float]:
    offers = session.execute(
        select(NormalizedOffer).where(
            NormalizedOffer.canonical_product_id == canonical_id
        )
    ).scalars().all()
    out: list[float] = []
    for o in offers:
        if o.price_rub is None or float(o.price_rub) <= 0:
            continue
        if not _is_usable_for_kpi(session, o.source_name, kpi_floor):
            continue
        out.append(float(o.price_rub))
    return out


def _our_price(
    session: Session, canonical_id: int, our_src: str
) -> float | None:
    o = session.execute(
        select(NormalizedOffer)
        .where(
            NormalizedOffer.canonical_product_id == canonical_id,
            NormalizedOffer.source_name == our_src,
        )
        .order_by(NormalizedOffer.loaded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if o is None or o.price_rub is None:
        return None
    return float(o.price_rub)


def position_for_canonical(
    session: Session, canonical_id: int, *, our_src: str | None = None
) -> MarketPosition:
    """
    Считает market position и рекомендуемое действие для каноникала.

    Args:
        session: Сессия БД.
        canonical_id: ID canonical_products.
        our_src: Имя 'нашего' источника (по умолчанию из env / EKF YML).
    """
    kpi_floor = min_usable_for_kpi()
    our_name = our_src or our_pricing_source()
    prices = _prices_for_canonical(session, canonical_id, kpi_floor)
    our_p = _our_price(session, canonical_id, our_name)

    if len(prices) < 2:
        return MarketPosition(
            canonical_id=canonical_id,
            status="insufficient_data",
            market_min=None,
            market_median=None,
            market_max=None,
            our_price=our_p,
            price_index=None,
            margin_pct=None,
            floor_price=None,
            simulated_cogs=None,
            recommended_action="review",
            competitors_count=0,
        )

    m_min = min(prices)
    m_max = max(prices)
    m_med = float(statistics.median(prices))
    sim_cogs = m_med * SIMULATED_COGS_FACTOR
    floor = sim_cogs / (1.0 - MIN_MARGIN_FLOOR) if (1.0 - MIN_MARGIN_FLOOR) > 0 else None
    pidx = (our_p / m_med) if (our_p and m_med) else None
    margin_pct = (
        (our_p - sim_cogs) / our_p
        if (our_p and sim_cogs is not None)
        else None
    )

    action = "review"
    if our_p and floor and our_p < floor:
        action = "raise_price"
    elif pidx and pidx > 1.0 + OUT_OF_MARKET_THRESHOLD:
        action = "lower_price"
    elif pidx and 0.95 <= pidx <= 1.05:
        action = "hold"
    else:
        action = "review"

    return MarketPosition(
        canonical_id=canonical_id,
        status="ok",
        market_min=m_min,
        market_median=m_med,
        market_max=m_max,
        our_price=our_p,
        price_index=pidx,
        margin_pct=margin_pct,
        floor_price=floor,
        simulated_cogs=sim_cogs,
        recommended_action=action,
        competitors_count=max(0, len(prices) - 1),
    )


@dataclass(frozen=True)
class MarketTableRow:
    """Строка для UI /market."""

    canonical_id: int
    vendor_code: str | None
    brand: str | None
    name: str | None
    our_price: float | None
    market_median: float | None
    price_index: float | None
    position_label: str
    action: str


def load_market_rows(
    session: Session, limit: int = 200, our_src: str | None = None
) -> list[MarketTableRow]:
    """
    Таблица market position по всем canonical с привязанными офферами.
    """
    our_name = our_src or our_pricing_source()
    ids = session.execute(
        select(CanonicalProduct.id).order_by(CanonicalProduct.id.desc()).limit(limit)
    ).scalars().all()
    out: list[MarketTableRow] = []
    for cid in ids:
        cp = session.get(CanonicalProduct, cid)
        if cp is None:
            continue
        pos = position_for_canonical(session, int(cid), our_src=our_name)
        if pos.status == "insufficient_data":
            continue
        pidx = pos.price_index
        if pidx and pidx > 1.05:
            plab = "expensive"
        elif pidx and pidx < 0.95:
            plab = "cheap"
        else:
            plab = "parity"
        out.append(
            MarketTableRow(
                canonical_id=int(cid),
                vendor_code=cp.vendor_code,
                brand=cp.brand,
                name=cp.canonical_name,
                our_price=pos.our_price,
                market_median=pos.market_median,
                price_index=pidx,
                position_label=plab,
                action=pos.recommended_action,
            )
        )
    return out


@dataclass(frozen=True)
class TodayActionStats:
    """Сводка для главной: сигналы и ревью."""

    out_of_market_n: int
    below_floor_n: int
    pending_fuzzy_n: int
    stale_source_n: int
    low_usable_n: int


def compute_today_action_counts(
    session: Session, our_src: str | None = None
) -> TodayActionStats:
    """
    Считает агрегаты для дашборда (приближение к '12/8/23' из плана).
    """
    our_name = our_src or our_pricing_source()
    kpi_floor = min_usable_for_kpi()

    out_n = 0
    floor_n = 0
    can_ids = session.execute(
        select(CanonicalProduct.id)
    ).scalars().all()
    for cid in can_ids:
        pos = position_for_canonical(session, int(cid), our_src=our_name)
        if pos.status != "ok":
            continue
        pidx = pos.price_index
        if pidx and pidx > 1.0 + OUT_OF_MARKET_THRESHOLD:
            out_n += 1
        if pos.our_price and pos.floor_price and pos.our_price < pos.floor_price:
            floor_n += 1

    pending_fuzzy = int(
        session.scalar(
            select(func.count(ProductMatch.id)).where(
                ProductMatch.match_kind == MATCH_KIND_FUZZY_TFIDF,
                ProductMatch.match_status == MATCH_STATUS_SUGGESTED,
            )
        )
        or 0
    )

    # stale: source_health not updated 48h
    from datetime import datetime, timedelta

    old = datetime.utcnow() - timedelta(hours=48)
    all_sh = session.execute(select(SourceHealth)).scalars().all()
    stale_n = sum(
        1
        for s in all_sh
        if s.last_loaded_at is None or s.last_loaded_at < old
    )
    low_n = sum(
        1
        for s in all_sh
        if s.usable_score is not None and s.usable_score < kpi_floor
    )

    return TodayActionStats(
        out_of_market_n=out_n,
        below_floor_n=floor_n,
        pending_fuzzy_n=pending_fuzzy,
        stale_source_n=stale_n,
        low_usable_n=low_n,
    )
