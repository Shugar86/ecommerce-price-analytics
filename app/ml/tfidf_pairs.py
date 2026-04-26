"""
Сопоставление наименований товаров через TF-IDF и косинусную близость.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class MatchPair:
    """Индексы пары в двух корпусах и оценка сходства."""

    idx_a: int
    idx_b: int
    score: float


def find_cross_shop_pairs(
    names_a: Sequence[str],
    names_b: Sequence[str],
    *,
    min_score: float = 0.28,
    max_pairs: int = 250,
) -> list[MatchPair]:
    """Строит пары между двумя списками наименований по косинусной близости TF-IDF.

    Args:
        names_a: Наименования магазина A.
        names_b: Наименования магазина B.
        min_score: Минимальный порог similarity [0, 1].
        max_pairs: Максимум пар в ответе (по убыванию score).

    Returns:
        Список пар с индексами в исходных списках.
    """
    if not names_a or not names_b:
        return []

    vectorizer = TfidfVectorizer(
        max_features=4096,
        ngram_range=(1, 2),
        min_df=1,
        lowercase=True,
    )
    matrix_a = vectorizer.fit_transform(list(names_a))
    matrix_b = vectorizer.transform(list(names_b))
    sim = cosine_similarity(matrix_a, matrix_b)

    pairs: list[MatchPair] = []
    for i in range(sim.shape[0]):
        for j in range(sim.shape[1]):
            s = float(sim[i, j])
            if s >= min_score:
                pairs.append(MatchPair(i, j, s))

    pairs.sort(key=lambda x: x.score, reverse=True)
    return pairs[:max_pairs]
