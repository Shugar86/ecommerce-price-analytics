"""
Сопоставление офферов: exact-first, TF-IDF только для кандидатов ручного ревью.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

FUZZY_TFIDF_REVIEW_MIN = 0.45
FUZZY_KIND_PREFIX = "fuzzy"


@dataclass(frozen=True)
class MatchResult:
    """Результат сопоставления пары офферов."""

    confidence: float
    kind: str
    is_automated: bool
    """False для fuzzy: только ручной ревью, не в KPI-автодействия."""


@runtime_checkable
class _Offerish(Protocol):
    """Минимальный контракт для match_pair (ORM или dict)."""

    @property
    def barcode(self) -> str | None: ...

    @property
    def brand(self) -> str | None: ...

    @property
    def vendor_code(self) -> str | None: ...

    @property
    def name(self) -> str | None: ...

    @property
    def category(self) -> str | None: ...


def normalize_barcode(value: str | None) -> str | None:
    """
    Нормализует штрихкод для сравнения (только цифры, без ведущих нулей для длины?).

    Оставляем цифры 8-14, strip.
    """
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value).strip())
    if len(digits) < 8:
        return None
    if len(digits) > 14:
        digits = digits[:14]
    return digits


def norm_brand(value: str | None) -> str:
    """
    Сравнение бренда: верхний регистр, сжатие пробелов.
    """
    if not value:
        return ""
    s = re.sub(r"\s+", " ", str(value).strip().upper())
    return s or ""


def norm_vendor_code(value: str | None) -> str:
    """
    Сравнение артикула: как в collector, без пробелов, upper.
    """
    if not value:
        return ""
    s = re.sub(r"\s+", " ", str(value).strip())
    s = s.replace(" ", "")
    return s.upper() or ""


def categories_compatible(a: str | None, b: str | None) -> bool:
    """
    Два непустых совпали бы по префиксу/вхождению или оба пусты (слабая совместимость).
    """
    if not a or not b:
        return True
    sa = a.strip().lower()[:200]
    sb = b.strip().lower()[:200]
    if sa == sb:
        return True
    return sa in sb or sb in sa or sa[:4] == sb[:4]


_MODEL_TOKEN_RE = re.compile(
    r"(?:[A-Z]{1,3}[-–]?\d{2,4}(?:[/-][A-Z0-9]+)?|"
    r"DS9\d{2}|S20[12]|iC60|ВА-?\d{2,3}|221-\d{3}|222-\d{3}|8909|8920|TX3|XML[- ]?\d+)"
)


def extract_model(name: str | None) -> str:
    """
    Грубое извлечение 'модели' из наименования (артикулоподобные токены).
    """
    if not name:
        return ""
    s = str(name).upper()
    m = _MODEL_TOKEN_RE.search(s)
    if m:
        return m.group(0).replace("–", "-")
    return ""


def _offer_get(
    o: Mapping[str, Any] | _Offerish, key: str
) -> Any:
    if isinstance(o, Mapping):
        return o.get(key)
    return getattr(o, key, None)


def match_pair(
    offer_a: Mapping[str, Any] | _Offerish,
    offer_b: Mapping[str, Any] | _Offerish,
) -> MatchResult | None:
    """
    Сопоставляет два оффера строгим по приоритету списку.

    Returns:
        MatchResult или None, если пары сопоставить нельзя (в т.ч. низкий fuzzy).
    """
    bc_a = normalize_barcode(_offer_get(offer_a, "barcode"))
    bc_b = normalize_barcode(_offer_get(offer_b, "barcode"))
    if bc_a and bc_b and bc_a == bc_b:
        return MatchResult(1.0, "exact_barcode", is_automated=True)

    br_a = norm_brand(_offer_get(offer_a, "brand"))  # type: ignore[arg-type]
    br_b = norm_brand(_offer_get(offer_b, "brand"))  # type: ignore[arg-type]
    v_a = norm_vendor_code(_offer_get(offer_a, "vendor_code"))  # type: ignore[arg-type]
    v_b = norm_vendor_code(_offer_get(offer_b, "vendor_code"))  # type: ignore[arg-type]

    if v_a and v_b and v_a == v_b and br_a and br_b and br_a == br_b:
        return MatchResult(0.92, "exact_vendor_brand", is_automated=True)

    cat_a = _offer_get(offer_a, "category")
    cat_b = _offer_get(offer_b, "category")
    if v_a and v_b and v_a == v_b and categories_compatible(
        str(cat_a) if cat_a else None,
        str(cat_b) if cat_b else None,
    ):
        return MatchResult(0.80, "exact_vendor", is_automated=True)

    n_a = _offer_get(offer_a, "name")
    n_b = _offer_get(offer_b, "name")
    m_a = extract_model(str(n_a) if n_a else None)
    m_b = extract_model(str(n_b) if n_b else None)
    if br_a and br_b and br_a == br_b and m_a and m_a == m_b:
        return MatchResult(0.75, "exact_brand_model", is_automated=True)

    t_a = str(n_a or "").strip()
    t_b = str(n_b or "").strip()
    if t_a and t_b:
        score = _tfidf_pair_score(t_a, t_b)
        if score is not None and score >= FUZZY_TFIDF_REVIEW_MIN:
            return MatchResult(
                float(round(score, 4)),
                "fuzzy_tfidf",
                is_automated=False,
            )
    return None


def _tfidf_pair_score(text_a: str, text_b: str) -> float | None:
    """Косинусная близость по TF-IDF для одной пары строк."""
    if not text_a or not text_b:
        return None
    try:
        vectorizer = TfidfVectorizer(
            max_features=256,
            ngram_range=(1, 2),
            min_df=1,
            lowercase=True,
        )
        m = vectorizer.fit_transform([text_a, text_b])
        sim = cosine_similarity(m[0:1], m[1:2])[0, 0]
        return float(sim)
    except (ValueError, TypeError) as e:
        # sklearn может упасть на слишком коротких/пустых токенах
        if "empty" in str(e).lower():
            return None
        return None


def is_fuzzy_for_review_only(kind: str) -> bool:
    """Fuzzy-совпадения не используются для автоматических pricing-действий."""
    return kind.startswith(FUZZY_KIND_PREFIX) or "fuzzy" in kind
