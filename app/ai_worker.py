"""
Аналитический воркер: периодический пересчёт аномалий цен, кандидатов сопоставления и прогнозов.

Основная очередь ревью — пары ``normalized_offers`` (TF-IDF из ``match_pair``, только fuzzy).
Опционально: legacy TF-IDF по ``Product`` (EKF ↔ TDM), ``USE_LEGACY_PRODUCT_MATCHING=1``.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

import numpy as np
from sklearn.linear_model import LinearRegression
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.database import (
    MATCH_KIND_FUZZY_JACCARD,
    MATCH_KIND_FUZZY_TFIDF,
    MATCH_STATUS_SUGGESTED,
    NormalizedOffer,
    NormalizedOfferMatch,
    PriceAnomaly,
    PriceForecast,
    PriceHistory,
    Product,
    ProductMatch,
    get_engine,
    get_session,
)
from app.matching.source_pairs import parse_ai_match_source_pairs
from app.ml.anomalies import detect_price_anomalies
from app.matching.text import tokenize_for_match
from app.ml.matching import extract_model, match_pair
from app.ml.tfidf_pairs import filter_greedy_one_to_one, find_cross_shop_pairs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Парсит int из env; пустая строка и отсутствие ключа = default (как в docker-compose)."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip(), 10)


def _env_float(name: str, default: float) -> float:
    """Парсит float из env; пустая строка = default."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return float(str(raw).strip().replace(",", "."))


AI_INTERVAL_SEC = _env_int("AI_WORKER_INTERVAL_SEC", 300)
MATCH_LIMIT_PER_SHOP = _env_int("AI_MATCH_LIMIT_PER_SHOP", 500)
# TF-IDF cosine floor (0–1). Default raised from 0.28 to limit weak title-only links.
# Scope: EKF vs TDM Electric only; see docs/PRODUCT_SCOPE.md.
AI_MATCH_MIN_SCORE = _env_float("AI_MATCH_MIN_SCORE", 0.45)
FORECAST_MIN_POINTS = _env_int("AI_FORECAST_MIN_POINTS", 5)
USE_LEGACY_PRODUCT_MATCHING = os.getenv(
    "USE_LEGACY_PRODUCT_MATCHING", ""
).strip().lower() in ("1", "true", "yes")
# Одинарная пара (легаси-совместимость, если AI_MATCH_SOURCE_PAIRS не задан)
AI_MATCH_NORMALIZED_LEFT = os.getenv("AI_MATCH_NORMALIZED_LEFT", "EKF YML")
AI_MATCH_NORMALIZED_RIGHT = os.getenv("AI_MATCH_NORMALIZED_RIGHT", "TDM Electric")
AI_MATCH_OFFER_CAP = _env_int("AI_MATCH_OFFER_CAP", 400)

_FUZZY_BLOCK_TOKENS = os.getenv(
    "AI_MATCH_BLOCK_NO_TOKEN_OVERLAP", "1"
).strip().lower() not in ("0", "false", "no", "")


def _skip_heavy_fuzzy_pair(a: NormalizedOffer, b: NormalizedOffer) -> bool:
    """
    Быстрый отсев пар без общих значимых токенов и без совпадения model-токена.

    Снижает число вызовов ``match_pair`` в вложенных циклах.
    """
    if not _FUZZY_BLOCK_TOKENS:
        return False
    na, nb = str(a.name or ""), str(b.name or "")
    ta, tb = tokenize_for_match(na), tokenize_for_match(nb)
    if ta and tb and (ta & tb):
        return False
    ma, mb = extract_model(na), extract_model(nb)
    if ma and mb and ma == mb:
        return False
    return True


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
    session = get_session(engine)
    try:
        _seed_demo_history(session)

        session.execute(delete(PriceAnomaly))
        # Only replace auto TF-IDF *suggestions*; keep analyst-confirmed/rejected rows.
        session.execute(
            delete(NormalizedOfferMatch).where(
                and_(
                    NormalizedOfferMatch.match_kind.in_(
                        [MATCH_KIND_FUZZY_TFIDF, MATCH_KIND_FUZZY_JACCARD]
                    ),
                    NormalizedOfferMatch.match_status == MATCH_STATUS_SUGGESTED,
                )
            )
        )
        if USE_LEGACY_PRODUCT_MATCHING:
            session.execute(
                delete(ProductMatch).where(
                    and_(
                        ProductMatch.match_kind == MATCH_KIND_FUZZY_TFIDF,
                        ProductMatch.match_status == MATCH_STATUS_SUGGESTED,
                    )
                )
            )
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

        source_pairs = parse_ai_match_source_pairs()

        existing_offer_pairs = {
            (int(r[0]), int(r[1]))
            for r in session.execute(
                select(
                    NormalizedOfferMatch.offer_low_id,
                    NormalizedOfferMatch.offer_high_id,
                )
            ).all()
        }

        offer_pairs_count = 0
        for left_name, right_name in source_pairs:
            if offer_pairs_count >= AI_MATCH_OFFER_CAP:
                break
            left_offers = session.scalars(
                select(NormalizedOffer)
                .where(NormalizedOffer.source_name == left_name)
                .order_by(NormalizedOffer.id)
                .limit(MATCH_LIMIT_PER_SHOP)
            ).all()
            right_offers = session.scalars(
                select(NormalizedOffer)
                .where(NormalizedOffer.source_name == right_name)
                .order_by(NormalizedOffer.id)
                .limit(MATCH_LIMIT_PER_SHOP)
            ).all()
            for a in left_offers:
                for b in right_offers:
                    if a.id == b.id:
                        continue
                    if _skip_heavy_fuzzy_pair(a, b):
                        continue
                    res = match_pair(a, b)
                    if res is None or res.is_automated:
                        continue
                    lo, hi = (int(a.id), int(b.id)) if a.id < b.id else (int(b.id), int(a.id))
                    if (lo, hi) in existing_offer_pairs:
                        continue
                    session.add(
                        NormalizedOfferMatch(
                            offer_low_id=lo,
                            offer_high_id=hi,
                            score=float(res.confidence),
                            method="name_jaccard",
                            match_kind=res.kind,
                            match_status=MATCH_STATUS_SUGGESTED,
                        )
                    )
                    existing_offer_pairs.add((lo, hi))
                    offer_pairs_count += 1
                    if offer_pairs_count >= AI_MATCH_OFFER_CAP:
                        break
                if offer_pairs_count >= AI_MATCH_OFFER_CAP:
                    break

        legacy_pairs_count = 0
        ekf_rows: list = []
        tdm_rows: list = []
        if USE_LEGACY_PRODUCT_MATCHING:
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
            if ekf_rows and tdm_rows:
                names_a = [str(r[1]) for r in ekf_rows]
                names_b = [str(r[1]) for r in tdm_rows]
                ids_a = [int(r[0]) for r in ekf_rows]
                ids_b = [int(r[0]) for r in tdm_rows]
                raw = find_cross_shop_pairs(
                    names_a,
                    names_b,
                    min_score=AI_MATCH_MIN_SCORE,
                    max_pairs=2000,
                )
                one_to_one = filter_greedy_one_to_one(raw)[:400]
                legacy_pairs_count = len(one_to_one)
                for pair in one_to_one:
                    ia, ib = ids_a[pair.idx_a], ids_b[pair.idx_b]
                    low, high = (ia, ib) if ia < ib else (ib, ia)
                    session.add(
                        ProductMatch(
                            product_low_id=low,
                            product_high_id=high,
                            score=pair.score,
                            method="tfidf_cosine",
                            match_kind=MATCH_KIND_FUZZY_TFIDF,
                            match_status=MATCH_STATUS_SUGGESTED,
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
        pairs_desc = source_pairs
        logger.info(
            "Цикл воркера: история=%s, fuzzy офферов=%s, пары=%s, legacy Product TF-IDF=%s",
            len(pids),
            offer_pairs_count,
            pairs_desc,
            legacy_pairs_count,
        )
    except Exception as exc:
        logger.exception("Ошибка цикла ИИ: %s", exc)
        session.rollback()
    finally:
        session.close()


def main() -> None:
    """Бесконечный цикл с паузой AI_WORKER_INTERVAL_SEC."""
    logger.info("Старт аналитического воркера, интервал %s с", AI_INTERVAL_SEC)
    while True:
        run_ai_cycle()
        time.sleep(AI_INTERVAL_SEC)


if __name__ == "__main__":
    main()
