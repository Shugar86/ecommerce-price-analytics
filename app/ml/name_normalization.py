"""
Объяснимая нормализация наименований товаров перед эвристическим сопоставлением.

Используется для повышения сходимости «грязных» прайсов без тяжёлого NLP: правила
детерминированы и пригодны для описания в ВКР.
"""

from __future__ import annotations

import re

# Известные бренды и аббревиатуры домена (электротовары / смежные каталоги) — к нижнему регистру.
_BRAND_PATTERN_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\biek\b", re.IGNORECASE), "iek"),
    (re.compile(r"\бекф\b|\bekf\b", re.IGNORECASE), "ekf"),
    (re.compile(r"\bwago\b", re.IGNORECASE), "wago"),
    (re.compile(r"\blegrand\b", re.IGNORECASE), "legrand"),
    (re.compile(r"\bschneider\b(?:\s+electric)?", re.IGNORECASE), "schneider"),
    (re.compile(r"\babb\b", re.IGNORECASE), "abb"),
    # Кабели / маркировка
    (re.compile(r"\bввгнг\b", re.IGNORECASE), "vvgng"),
)


_UNITS_RE = re.compile(
    r"\b(шт\.?|pcs\.?|pc\.?|уп\.?|упак\.?|компл\.?|комплект)\b",
    re.IGNORECASE,
)

_MULTISPACE_RE = re.compile(r"\s+")


def normalize_title_for_matching(title: str) -> str:
    """Приводит название к виду, удобному для эвристик ``name_only_score``.

    Последовательность шагов фиксирована:

    Args:
        title: сырое наименование из фида.

    Returns:
        Нормализованная строка (нижний регистр, без лишних пробелов). Пустые входы
        дают пустую строку.

    Note:
        Не удаляет цифры и маркеры вроде ``2x1.5``, ``16a``, ``ip44`` —
        они нужны ``extract_model`` и Jaccard по латинским токенам.
    """
    if not title:
        return ""
    s = str(title).strip().replace("ё", "е").lower()
    s = (
        s.replace("×", "x")
        .replace("/", " ")
        .replace("\\", " ")
    )
    s = _UNITS_RE.sub("qty", s)
    for rx, repl in _BRAND_PATTERN_REPLACEMENTS:
        s = rx.sub(repl, s)
    # Пунктуация «в пробел», кроме дефисов внутри модельных блоков сохранится как дефис.
    for ch in '.,;:!?()[]{}+"\'’«»':
        s = s.replace(ch, " ")
    s = _MULTISPACE_RE.sub(" ", s).strip()
    return s


def normalize_title_for_token_overlap(title: str) -> str:
    """Нормализация для быстрого отсева пар без пересечения токенов (см. ``ai_worker``).

    Args:
        title: сырое наименование.

    Returns:
        Строка после :func:`normalize_title_for_matching` без дополнительных шагов.
    """
    return normalize_title_for_matching(title)
