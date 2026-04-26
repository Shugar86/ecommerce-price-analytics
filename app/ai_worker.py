"""
ИИ-воркер: периодический пересчёт аномалий цен, TF-IDF сопоставлений и прогнозов.

Запускается отдельным контейнером. Пишет результаты в PostgreSQL.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

import numpy as np
from sklearn.linear_model import LinearRegression
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import (
    PriceAnomaly,
    PriceForecast,
    PriceHistory,
    Product,
    ProductMatch,
    get_engine,
    get_session,
    init_db,
)
from app.ml.anomalies import detect_price_anomalies
from app.ml.tfidf_pairs import find_cross_shop_pairs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

AI_INTERVAL_SEC = int(os.getenv("AI_WORKER_INTERVAL_SEC", "300"))
MATCH_LIMIT_PER_SHOP = int(os.getenv("AI_MATCH_LIMIT_PER_SHOP", "500"))
FORECAST_MIN_POINTS = int(os.getenv("AI_FORECAST_MIN_POINTS", "5"))


def _history_prices(session: Session, product_id: int, *, limit: int = 40) -> list[float]:
    """Возвращает цены по возрастанию времени."""
    rows = session.execute(
        select(PriceHistory.price_in_rub)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.collected_at.asc())
        .limit(limit)
    ).all()
    return [float(r[0]) for r in rows]


def _seed_demo_history(session: Session) -> None:
    """Добавляет синтетическую историю для демонстрации графиков (однократно на товар)."""
    if os.getenv("SEED_DEMO_HISTORY", "").lower() not in ("1", "true", "yes"):
        return

    rows = session.execute(
        select(Product.id, Product.price_in_rub, Product.source_shop, Product.external_id)
        .order_by(Product.id)
        .limit(80)
    ).all()

    now = datetime.utcnow()
    added = 0
    for pid, price, shop, ext in rows:
        cnt = session.scalar(
            select(func.count(PriceHistory.id)).where(PriceHistory.product_id == pid)
        ) or 0
        if int(cnt) >= 3:
            continue
        base = float(price)
        if base <= 0:
            continue
        deltas = [0.0, 0.03, -0.02, 0.04, -0.15]  # последняя точка имитирует «скидку»
        for k, d in enumerate(deltas):
            session.add(
                PriceHistory(
                    product_id=int(pid),
                    price_in_rub=max(0.01, base * (1.0 + d)),
                    source_shop=str(shop),
                    external_id=str(ext),
                    collected_at=now - timedelta(hours=(len(deltas) - k) * 6),
                )
            )
            added += 1
    if added:
        logger.info("Демо-история: добавлено точек %s (SEED_DEMO_HISTORY).", added)


def run_ai_cycle() -> None:
    """Один проход: очистка старых результатов, расчёт и запись."""
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        _seed_demo_history(session)

        session.execute(delete(PriceAnomaly))
        session.execute(delete(ProductMatch))
        session.execute(delete(PriceForecast))

        pids = session.execute(
            select(PriceHistory.product_id)
            .group_by(PriceHistory.product_id)
            .having(func.count(PriceHistory.id) >= 3)
        ).scalars().all()

        now = datetime.utcnow()
        for pid in pids:
            series = _history_prices(session, int(pid), limit=50)
            if len(series) < 3:
                continue
            for hit in detect_price_anomalies(series):
                session.add(
                    PriceAnomaly(
                        product_id=int(pid),
                        detected_at=now,
                        anomaly_type=hit.anomaly_type,
                        severity=hit.severity,
                        detail=hit.detail,
                        price_at_detection=hit.price_at_detection,
                    )
                )

        ekf_rows = session.execute(
            select(Product.id, Product.name)
            .where(Product.source_shop == "EKF")
            .limit(MATCH_LIMIT_PER_SHOP)
        ).all()
        tdm_rows = session.execute(
            select(Product.id, Product.name)
            .where(Product.source_shop == "TDM Electric")
            .limit(MATCH_LIMIT_PER_SHOP)
        ).all()

        pairs_count = 0
        if ekf_rows and tdm_rows:
            names_a = [str(r[1]) for r in ekf_rows]
            names_b = [str(r[1]) for r in tdm_rows]
            ids_a = [int(r[0]) for r in ekf_rows]
            ids_b = [int(r[0]) for r in tdm_rows]
            pairs = find_cross_shop_pairs(names_a, names_b, min_score=0.28, max_pairs=400)
            pairs_count = len(pairs)
            for pair in pairs:
                ia, ib = ids_a[pair.idx_a], ids_b[pair.idx_b]
                low, high = (ia, ib) if ia < ib else (ib, ia)
                session.add(
                    ProductMatch(
                        product_low_id=low,
                        product_high_id=high,
                        score=pair.score,
                        method="tfidf_cosine",
                    )
                )

        for pid in pids:
            rows = session.execute(
                select(PriceHistory.price_in_rub)
                .where(PriceHistory.product_id == pid)
                .order_by(PriceHistory.collected_at.asc())
                .limit(25)
            ).all()
            if len(rows) < FORECAST_MIN_POINTS:
                continue
            y = np.array([float(r[0]) for r in rows], dtype=float)
            x = np.arange(len(y), dtype=float).reshape(-1, 1)
            model = LinearRegression().fit(x, y)
            nxt = float(model.predict(np.array([[float(len(y))]]))[0])
            session.add(
                PriceForecast(
                    product_id=int(pid),
                    forecast_price_rub=max(0.01, nxt),
                    method="linear_trend",
                    forecast_for=now + timedelta(days=1),
                )
            )

        session.commit()
        logger.info(
            "Цикл ИИ завершён: товаров с историей=%s, EKF=%s, TDM=%s, пар TF-IDF=%s",
            len(pids),
            len(ekf_rows),
            len(tdm_rows),
            pairs_count,
        )
    except Exception as exc:
        logger.exception("Ошибка цикла ИИ: %s", exc)
        session.rollback()
    finally:
        session.close()


def main() -> None:
    """Бесконечный цикл с паузой AI_WORKER_INTERVAL_SEC."""
    logger.info("Старт ИИ-воркера, интервал %s с", AI_INTERVAL_SEC)
    while True:
        run_ai_cycle()
        time.sleep(AI_INTERVAL_SEC)


if __name__ == "__main__":
    main()
