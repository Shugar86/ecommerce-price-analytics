"""Smoke test for the /compare matching logic (runs without Telegram).

Run inside the `bot` container:
  python /tmp/test_compare.py
"""

from __future__ import annotations

from sqlalchemy import select

from app.matching.text import similarity_jaccard_tokens
from app.database import Product, get_engine, get_session


def main() -> None:
    """Run a simple pairing test for fridge-like items."""
    engine = get_engine()
    session = get_session(engine)
    try:
        query = "холодиль"
        limit_per_shop = 10

        tbm = session.execute(
            select(Product)
            .where(Product.source_shop == "TBM Market", Product.name.ilike(f"%{query}%"))
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()

        gala = session.execute(
            select(Product)
            .where(Product.source_shop == "GalaCentre", Product.name.ilike(f"%{query}%"))
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()

        print(f"TBM={len(tbm)} GalaCentre={len(gala)}")
        if not tbm or not gala:
            raise SystemExit("Need results in both shops to test pairing.")

        best = []
        for t in tbm:
            best_score = -1.0
            best_item = None
            for g in gala:
                s = similarity_jaccard_tokens(t.name, g.name)
                if s > best_score:
                    best_score = s
                    best_item = g
            assert best_item is not None
            best.append((best_score, t, best_item))

        best.sort(key=lambda x: x[0], reverse=True)
        for score, t, g in best[:5]:
            print(
                f"score={score:.2f} "
                f"TBM={t.price_in_rub:.2f} ({t.name[:55]}) "
                f"|| GALA={g.price_in_rub:.2f} ({g.name[:55]})"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()


