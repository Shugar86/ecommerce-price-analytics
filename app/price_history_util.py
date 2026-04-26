"""
Запись истории цен после UPSERT товаров в collector.

Добавляет строку в ``price_history``, если товар новый или цена в рублях изменилась.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import PriceHistory, Product

logger = logging.getLogger(__name__)

_HISTORY_EPS = 1e-4


def record_price_change(
    session: Session,
    *,
    external_id: str,
    source_shop: str,
    collected_at: Optional[datetime] = None,
) -> None:
    """Добавить точку истории, если цена изменилась или истории ещё не было.

    Вызывать в той же транзакции сразу после UPSERT товара.

    Args:
        session: Активная сессия SQLAlchemy.
        external_id: Уникальный ключ товара (как в ``products.external_id``).
        source_shop: Название источника (магазина).
        collected_at: Момент наблюдения (UTC). По умолчанию — текущее время.

    Note:
        Сравнение с последней записью истории уменьшает дубли при неизменной цене.
    """
    collected_at = collected_at or datetime.utcnow()
    try:
        prod = session.execute(
            select(Product).where(Product.external_id == external_id)
        ).scalar_one_or_none()
        if prod is None:
            return

        last_price = session.execute(
            select(PriceHistory.price_in_rub)
            .where(PriceHistory.product_id == prod.id)
            .order_by(PriceHistory.collected_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        current = float(prod.price_in_rub)
        if last_price is not None and abs(float(last_price) - current) <= _HISTORY_EPS:
            return

        session.add(
            PriceHistory(
                product_id=prod.id,
                price_in_rub=current,
                source_shop=source_shop,
                external_id=external_id,
                collected_at=collected_at,
            )
        )
    except Exception as exc:
        logger.warning("Не удалось записать историю цены для %s: %s", external_id, exc)
