"""
Конфигурация пар источников для fuzzy-кандидатов (normalized_offers).

Используется в ``ai_worker`` и веб-интерфейсе (подсказки аналитику).
"""

from __future__ import annotations

import os


def parse_ai_match_source_pairs() -> list[tuple[str, str]]:
    """
    Парсит ``AI_MATCH_SOURCE_PAIRS`` или fallback на LEFT/RIGHT.

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
    if not pairs:
        a = (os.getenv("AI_MATCH_NORMALIZED_LEFT") or "EKF YML").strip()
        b = (os.getenv("AI_MATCH_NORMALIZED_RIGHT") or "TDM Electric").strip()
        if a and b:
            pairs.append((a, b))
    return pairs
