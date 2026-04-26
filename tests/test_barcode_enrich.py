"""Обогащение normalized_offers из barcode_reference."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.collectors.barcode_enrich import enrich_normalized_offers_from_reference
from app.collectors.normalized_io import replace_normalized_offers
from app.database import BarcodeReference, Base, NormalizedOffer


def test_enrich_fills_vendor_and_brand() -> None:
    """Пустые поля заполняются по штрихкоду."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    s.add(
        BarcodeReference(
            barcode="1234567890123",
            article="ART-1",
            vendor="VendorCo",
        )
    )
    o = NormalizedOffer(
        source_name="EKF YML",
        barcode="1234567890123",
        price_rub=1.0,
    )
    s.add(o)
    s.commit()
    n = enrich_normalized_offers_from_reference(s)
    assert n == 1
    s.refresh(o)
    assert o.vendor_code == "ART-1"
    assert o.brand == "VendorCo"
    s.close()


def test_replace_normalized_enriches_from_reference() -> None:
    """replace_normalized_offers подставляет brand/vendor из barcode_reference."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    s.add(
        BarcodeReference(
            barcode="8765432109876",
            article="Z-9",
            vendor="ZedInc",
        )
    )
    s.commit()
    rows = [
        {
            "name": "Item",
            "price_rub": 99.0,
            "barcode": "8765432109876",
            "external_id": "t1",
        }
    ]
    replace_normalized_offers(s, "TestSrc", "http://x", rows)
    s.commit()
    o = s.scalars(
        select(NormalizedOffer).where(NormalizedOffer.source_name == "TestSrc")
    ).one()
    assert o.vendor_code == "Z-9"
    assert o.brand == "ZedInc"
    s.close()
