"""
Интеграция OWWA (Tier C) — внешний мониторинг цен маркетплейсов.

Полноценные вызовы API (POST /v1/items/add, list) требуют учётных данных;
при пустом ``OWWA_API_CLIENT_ID`` / токене — только лог, без сети.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.owwa.ru/fl_0007/hs/api"


def _owwa_enabled() -> bool:
    return os.getenv("ENABLE_OWWA", "").strip().lower() in ("1", "true", "yes")


def run_owwa_ingest_stub(session: Session) -> int:
    """
    Точка расширения: загрузка в ``owwa_listings``.

    Returns:
        Число вставленных строк (0, пока нет рабочих учётных данных и контракта).
    """
    if not _owwa_enabled():
        return 0
    client = (os.getenv("OWWA_API_CLIENT_ID") or "").strip()
    token = (os.getenv("OWWA_API_TOKEN") or "").strip()
    if not client and not token:
        logger.info(
            "OWWA: ENABLE_OWWA=1, но OWWA_API_CLIENT_ID/OWWA_API_TOKEN не заданы — "
            "ингест пропущен (заглушка Tier C)"
        )
        return 0
    base = (os.getenv("OWWA_API_BASE") or _DEFAULT_BASE).rstrip("/")
    logger.info(
        "OWWA: заглушка: credentials заданы, base=%s — реализация POST/list вынесена в доработку",
        base,
    )
    return 0
