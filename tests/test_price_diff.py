"""Страница /price-diff: агрегат по canonical_products + normalized_offers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, CanonicalProduct, NormalizedOffer
from app.web.services import list_price_diff_rows


def test_list_price_diff_two_sources() -> None:
    """Два источника с разной ценой дают одну строку с положительной дельтой."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    cp = CanonicalProduct(canonical_name="Item", brand="BR", vendor_code="V1")
    s.add(cp)
    s.flush()
    s.add(
        NormalizedOffer(
            source_name="ShopA",
            name="Item",
            price_rub=100.0,
            canonical_product_id=cp.id,
            vendor_code="V1",
        )
    )
    s.add(
        NormalizedOffer(
            source_name="ShopB",
            name="Item",
            price_rub=130.0,
            canonical_product_id=cp.id,
            vendor_code="V1",
        )
    )
    s.commit()
    rows = list_price_diff_rows(s, limit=20)
    assert len(rows) == 1
    assert rows[0].delta_pct == 30.0
    assert rows[0].min_source == "ShopA"
    assert rows[0].max_source == "ShopB"
    s.close()
