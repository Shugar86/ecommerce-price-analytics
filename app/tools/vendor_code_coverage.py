"""
Сводка заполненности vendor_code / barcode в normalized_offers по источникам.

Запуск из корня репозитория::

    python -m app.tools.vendor_code_coverage
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import case, func, select

from app.database import NormalizedOffer, get_engine, get_session, init_db

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        vc_nz = func.sum(
            case((NormalizedOffer.vendor_code.isnot(None), 1), else_=0)
        )
        bc_nz = func.sum(
            case((NormalizedOffer.barcode.isnot(None), 1), else_=0)
        )
        rows = session.execute(
            select(
                NormalizedOffer.source_name,
                func.count(NormalizedOffer.id),
                vc_nz,
                bc_nz,
            )
            .group_by(NormalizedOffer.source_name)
            .order_by(NormalizedOffer.source_name)
        ).all()
        print(f"{'source_name':<42} {'rows':>10} {'with_vc':>10} {'with_bc':>10} {'vc_%':>8}")
        for name, n, vc_n, bc_n in rows:
            n = int(n or 0)
            vc = int(vc_n or 0)
            bc = int(bc_n or 0)
            vc_pct = 100.0 * vc / n if n else 0.0
            print(f"{name:<42} {n:>10} {vc:>10} {bc:>10} {vc_pct:>7.1f}%")
    finally:
        session.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("%s", exc)
        sys.exit(1)
