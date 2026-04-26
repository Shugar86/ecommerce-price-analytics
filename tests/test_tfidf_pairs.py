"""Тесты TF-IDF сопоставления наименований."""

from __future__ import annotations

from app.ml.tfidf_pairs import find_cross_shop_pairs


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
