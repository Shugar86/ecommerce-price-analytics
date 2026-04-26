"""
Конфигурация пар источников для fuzzy-кандидатов (normalized_offers).

Используется в ``ai_worker`` и веб-интерфейсе (подсказки аналитику).
"""

from __future__ import annotations

import logging
import os

from app.collectors.local_price_defaults import LOCAL_PRICE_SOURCE_NAME_DEFAULT

logger = logging.getLogger(__name__)


def local_price_source_name() -> str:
    """Каноническое имя локального прайса для default-пар (должно совпадать с ETL)."""
    v = (os.getenv("LOCAL_PRICE_SOURCE_NAME") or "").strip()
    return v or LOCAL_PRICE_SOURCE_NAME_DEFAULT


def default_normalized_match_pairs() -> list[tuple[str, str]]:
    """
    Пары по умолчанию: сначала кириллические хабы (TDM, Комплект-Сервис, Syperopt),
    затем локальный прайс, в конце EKF YML ↔ TDM.

    Имена совпадают с ``NormalizedOffer.source_name`` после ETL.
    """
    loc = local_price_source_name()
    return [
        ("TDM Electric", "IEK (Комплект-Сервис)"),
        ("TDM Electric", "EKF (Комплект-Сервис)"),
        ("IEK (Комплект-Сервис)", "Syperopt XLSX"),
        ("TDM Electric", "Schneider Electric (КС)"),
        ("TDM Electric", "Legrand (Комплект-Сервис)"),
        ("TDM Electric", "WAGO (Комплект-Сервис)"),
        # Локальный файл zayavka — номенклатура ТДМ; с ИЭК его не сравниваем по умолчанию.
        ("TDM Electric", loc),
        ("EKF YML", "TDM Electric"),
    ]


def _single_pair_fallback_enabled() -> bool:
    """Легаси: одна пара LEFT|RIGHT, как до расширенного дефолта."""
    return os.getenv("AI_MATCH_SINGLE_PAIR_FALLBACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def parse_ai_match_source_pairs() -> list[tuple[str, str]]:
    """
    Парсит ``AI_MATCH_SOURCE_PAIRS`` или расширенный дефолт / fallback.

    Формат: ``"A|B;C|D"`` — точка с запятой между парами, вертикальная черта между левым и правым именем.

    Returns:
        Список пар (source_name_left, source_name_right), непустой при валидном env.
    """
    raw = (os.getenv("AI_MATCH_SOURCE_PAIRS") or "").strip()
    pairs: list[tuple[str, str]] = []
    if raw:
        for seg in raw.split(";"):
            seg = seg.strip()
            if not seg or "|" not in seg:
                continue
            left, right = seg.split("|", 1)
            a, b = left.strip(), right.strip()
            if a and b:
                pairs.append((a, b))
        if pairs:
            return pairs
        logger.warning(
            "AI_MATCH_SOURCE_PAIRS задан, но не распарсился ни один сегмент — "
            "используется расширенный дефолт"
        )
        return list(default_normalized_match_pairs())
    if _single_pair_fallback_enabled():
        a = (os.getenv("AI_MATCH_NORMALIZED_LEFT") or "EKF YML").strip()
        b = (os.getenv("AI_MATCH_NORMALIZED_RIGHT") or "TDM Electric").strip()
        if a and b:
            return [(a, b)]
        return []
    return list(default_normalized_match_pairs())
