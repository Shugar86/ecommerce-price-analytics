"""Интеграционные проверки KPI с SQLite in-memory."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analytics.price_intelligence import position_for_canonical
from app.database import Base, CanonicalProduct, NormalizedOffer, SourceHealth


@pytest.fixture
def pi_session():
    """Сессия с полной схемой metadata (все таблицы моделей)."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()


def test_position_raise_price_below_floor(pi_session) -> None:
    """Наша цена ниже floor → raise_price (медиана по всем офферам каноникала)."""
    s = pi_session
    s.add(SourceHealth(source_name="EKF YML", usable_score=0.7))
    s.add(SourceHealth(source_name="TDM Electric", usable_score=0.7))
    cp = CanonicalProduct(vendor_code="ABC", brand="B", match_confidence=0.9)
    s.add(cp)
    s.flush()
    s.add_all(
        [
            NormalizedOffer(
                source_name="EKF YML",
                price_rub=50.0,
                vendor_code="ABC",
                brand="B",
                canonical_product_id=cp.id,
            ),
            NormalizedOffer(
                source_name="TDM Electric",
                price_rub=100.0,
                vendor_code="ABC",
                brand="B",
                canonical_product_id=cp.id,
            ),
            NormalizedOffer(
                source_name="TDM Electric",
                price_rub=110.0,
                vendor_code="ABC",
                brand="B",
                canonical_product_id=cp.id,
            ),
        ]
    )
    s.commit()
    pos = position_for_canonical(s, cp.id, our_src="EKF YML")
    assert pos.status == "ok"
    assert pos.recommended_action == "raise_price"


def test_position_lower_price_out_of_market(pi_session) -> None:
    """Индекс цены сильно выше медианы → lower_price."""
    s = pi_session
    s.add(SourceHealth(source_name="EKF YML", usable_score=0.7))
    s.add(SourceHealth(source_name="TDM Electric", usable_score=0.7))
    cp = CanonicalProduct(vendor_code="X1", brand="B", match_confidence=0.9)
    s.add(cp)
    s.flush()
    s.add_all(
        [
            NormalizedOffer(
                source_name="EKF YML",
                price_rub=130.0,
                vendor_code="X1",
                brand="B",
                canonical_product_id=cp.id,
            ),
            NormalizedOffer(
                source_name="TDM Electric",
                price_rub=100.0,
                vendor_code="X1",
                brand="B",
                canonical_product_id=cp.id,
            ),
            NormalizedOffer(
                source_name="TDM Electric",
                price_rub=100.0,
                vendor_code="X1",
                brand="B",
                canonical_product_id=cp.id,
            ),
        ]
    )
    s.commit()
    pos = position_for_canonical(s, cp.id, our_src="EKF YML")
    assert pos.status == "ok"
    assert pos.recommended_action == "lower_price"
