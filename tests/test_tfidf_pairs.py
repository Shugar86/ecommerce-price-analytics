"""Тесты TF-IDF сопоставления наименований."""

from __future__ import annotations

from app.ml.tfidf_pairs import filter_greedy_one_to_one, find_cross_shop_pairs


def test_similar_russian_names_high_score() -> None:
    """Близкие строки должны получить заметный score."""
    a = ["Переходник E14-GU10 белый TDM"]
    b = ["Переходник E14 GU10 белый EKF Proxima"]
    pairs = find_cross_shop_pairs(a, b, min_score=0.15, max_pairs=5)
    assert pairs
    assert pairs[0].score >= 0.15


def test_unrelated_low_score() -> None:
    """Несвязанные названия не попадают в результат при высоком пороге."""
    a = ["Ноутбук ASUS"]
    b = ["Кабель HDMI 2м"]
    pairs = find_cross_shop_pairs(a, b, min_score=0.9, max_pairs=5)
    assert not pairs


def test_greedy_one_to_one_respects_unique_indices() -> None:
    """Greedy matching does not reuse the same catalog row on either side."""
    a = ["Same A1", "Same A2", "Unique A3"]
    b = ["Same B1", "Same B2", "Unique B3"]
    raw = find_cross_shop_pairs(a, b, min_score=0.01, max_pairs=50)
    assert len(raw) >= 3
    slim = filter_greedy_one_to_one(raw)
    used_a = {p.idx_a for p in slim}
    used_b = {p.idx_b for p in slim}
    assert len(used_a) == len(slim)
    assert len(used_b) == len(slim)
    assert len(slim) <= 3
