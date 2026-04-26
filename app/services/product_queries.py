"""Reusable read queries for the Telegram bot (product search / compare / shop stats)."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Product

_DEFAULT_FIND_SHOP_ORDER: Sequence[str] = (
    "EKF",
    "TDM Electric",
    "TBM Market",
    "GalaCentre",
    "FakeStore",
)


def shops_with_product_counts_desc(session: Session) -> list[tuple[str, int]]:
    """Per-shop product counts, descending by count (same as /stats, /shops)."""
    rows = session.execute(
        select(Product.source_shop, func.count(Product.id))
        .group_by(Product.source_shop)
        .order_by(func.count(Product.id).desc())
    ).all()
    return [(r[0], int(r[1])) for r in rows if r and r[0]]


def find_products_by_name_substring(
    session: Session,
    q_norm: str,
    *,
    shop_filter: Optional[str] = None,
    per_shop_limit: int = 4,
    single_shop_limit: int = 15,
) -> list[Product]:
    """Products matching ``name_norm`` ILIKE; either one shop or a few rows per default shop list."""
    if shop_filter:
        stmt = (
            select(Product)
            .where(
                Product.source_shop == shop_filter,
                Product.name_norm.ilike(f"%{q_norm}%"),
            )
            .order_by(Product.price_in_rub)
            .limit(single_shop_limit)
        )
        return list(session.execute(stmt).scalars().all())
    out: list[Product] = []
    for s in _DEFAULT_FIND_SHOP_ORDER:
        rows = (
            session.execute(
                select(Product)
                .where(Product.source_shop == s, Product.name_norm.ilike(f"%{q_norm}%"))
                .order_by(Product.price_in_rub)
                .limit(per_shop_limit)
            )
            .scalars()
            .all()
        )
        out.extend(rows)
    return out


def compare_top_by_shops(
    session: Session,
    shop_a: str,
    shop_b: str,
    q_norm: str,
    *,
    limit_per_shop: int = 40,
) -> tuple[list[Product], list[Product]]:
    """Candidates for /compare: cheapest-first cap per shop."""
    a_items = list(
        session.execute(
            select(Product)
            .where(
                Product.source_shop == shop_a,
                Product.name_norm.ilike(f"%{q_norm}%"),
            )
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()
    )
    b_items = list(
        session.execute(
            select(Product)
            .where(
                Product.source_shop == shop_b,
                Product.name_norm.ilike(f"%{q_norm}%"),
            )
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()
    )
    return a_items, b_items
