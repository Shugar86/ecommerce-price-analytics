"""Product name normalization and heuristic similarity for price analytics."""

from __future__ import annotations

import re
from typing import Iterable

# Used for `name_norm` in DB: same contract as former collector._normalize_name.
_NAME_NORM_RE = re.compile(r"\s+")

# Cross-shop "model token" and latin token heuristics (bot /compare).
_LAT_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_MODEL_TOKEN_RE = re.compile(
    r"(?=.*[a-z])(?=.*\d)[a-z0-9]{3,32}$",
    re.IGNORECASE,
)

_RU_TO_LAT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ы": "y",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ь": "",
    "ъ": "",
}


def _to_latin(text: str) -> str:
    t = text.lower().replace("ё", "е")
    out: list[str] = []
    for ch in t:
        if "а" <= ch <= "я" or ch in ("ё", "ь", "ъ"):
            out.append(_RU_TO_LAT.get(ch, ""))
        else:
            out.append(ch)
    return "".join(out)


def normalize_name_for_search(text: str) -> str:
    """Normalize a product name for `name_norm` / ILIKE search (matches DB pipeline).

    Args:
        text: Raw product title from a feed or API.

    Returns:
        Lowercased, punctuation flattened to spaces, max 600 characters.
    """
    cleaned = (
        text.lower()
        .replace("ё", "е")
        .replace("/", " ")
        .replace("\\\\", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("[", " ")
        .replace("]", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("|", " ")
        .replace("+", " ")
        .replace("—", " ")
        .replace("–", " ")
        .replace("-", " ")
        .replace('"', " ")
        .replace("'", " ")
    )
    cleaned = _NAME_NORM_RE.sub(" ", cleaned).strip()
    return cleaned[:600]


def _normalize_for_match(text: str) -> str:
    """Normalize + transliterate to latin for cross-shop name-only scoring."""
    t = _to_latin(text)
    t = (
        t.replace("×", "x")
        .replace("/", " ")
        .replace("\\\\", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("[", " ")
        .replace("]", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("|", " ")
        .replace("+", " ")
        .replace("—", " ")
        .replace("–", " ")
        .replace("-", " ")
        .replace('"', " ")
        .replace("'", " ")
    )
    t = _NAME_NORM_RE.sub(" ", t).strip()
    return t


def _tokens_lat(text: str) -> set[str]:
    norm = _normalize_for_match(text)
    return {t for t in _LAT_TOKEN_RE.findall(norm) if len(t) >= 3}


def _model_tokens(tokens: Iterable[str]) -> set[str]:
    return {t for t in tokens if _MODEL_TOKEN_RE.match(t) is not None}


def _word_tokens(tokens: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for t in tokens:
        if t.isdigit():
            continue
        if any("a" <= ch <= "z" for ch in t) and len(t) >= 5:
            out.add(t)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def jaccard_similarity_sets(a: set[str], b: set[str]) -> float:
    """Jaccard index on two sets of string tokens. Returns 0 if either set is empty."""
    return _jaccard(a, b)


def transliterate_ru_to_latin(s: str) -> str:
    """Public transliteration used by overlap/CLI token pipelines (same rules as /compare heuristics)."""
    return _to_latin(s)


def normalize_for_match_scoring(s: str) -> str:
    """Transliterate RU to latin and flatten punctuation; base for alnum token extraction in reports.

    This matches the internal chain used for ``name_only_score`` / EKF-style slugs. Reports that need
    different model-token regexes keep their own patterns; only the normalization path is shared.
    """
    return _normalize_for_match(s)


def name_only_score(a: str, b: str) -> float:
    """Name-only similarity for dirty RU data + EKF-style latin slugs (bot /compare)."""
    ta = _tokens_lat(a)
    tb = _tokens_lat(b)
    ma, mb = _model_tokens(ta), _model_tokens(tb)
    wa, wb = _word_tokens(ta), _word_tokens(tb)

    if ma and mb:
        if not (ma & mb):
            return 0.0
        return 0.8 * _jaccard(ma, mb) + 0.2 * _jaccard(wa, wb)

    if len(wa) >= 2 and len(wb) >= 2 and len(wa & wb) >= 1:
        return _jaccard(wa, wb)
    return 0.0


def item_type(name: str) -> str:
    """Rough product type to avoid false pairs (e.g. fridge vs fridge magnet)."""
    n = name.lower().replace("ё", "е")
    if "магнит" in n:
        return "magnet"
    if "открываш" in n:
        return "opener"
    if "микроволновка" in n:
        return "microwave"
    if "тарелка" in n and "микроволнов" in n:
        return "microwave_plate"
    if "холодильник" in n or "холодильная камера" in n:
        return "fridge"
    if "контейнер" in n:
        return "container"
    if "поглот" in n or "освеж" in n:
        return "odor"
    return "other"


def tokenize_for_match(text: str) -> set[str]:
    """Tokenize a product name for Jaccard similarity (looser than `name_only_score`)."""
    cleaned = (
        text.lower()
        .replace("ё", "е")
        .replace("/", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    return {p for p in parts if len(p) >= 3}


def similarity_jaccard_tokens(a: str, b: str) -> float:
    """Jaccard similarity over whitespace tokens (length >= 3)."""
    ta = tokenize_for_match(a)
    tb = tokenize_for_match(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union
