"""Tests for shared product-text normalization and heuristic similarity."""

from app.matching.text import (
    item_type,
    jaccard_similarity_sets,
    name_only_score,
    normalize_name_for_search,
    similarity_jaccard_tokens,
    tokenize_for_match,
    transliterate_ru_to_latin,
)


def test_normalize_name_for_search_replaces_punctuation() -> None:
    raw = "Лампа  E14/GU10  (упак, 2 шт.)"
    got = normalize_name_for_search(raw)
    assert "лампа" in got
    assert "e14" in got and "gu10" in got
    assert "/" not in got
    assert len(got) <= 600


def test_item_type_fridge_vs_magnet() -> None:
    assert item_type("Холодильник двухкамерный") == "fridge"
    assert item_type("Магнит на холодильник") == "magnet"


def test_name_only_score_model_tokens_ekf_style() -> None:
    a = "Лампа LED E14 GU10 7W EKF"
    b = "led lamp e14 gu10 7w tdm"
    s = name_only_score(a, b)
    assert s > 0.2


def test_name_only_score_no_model_overlap_zero() -> None:
    a = "Щётка стеклоочистителя 500мм"
    b = "Светильник настенный e27 60w"
    assert name_only_score(a, b) == 0.0


def test_similarity_jaccard_tokens() -> None:
    a = "samsung galaxy note phone"
    b = "phone samsung note series"
    assert similarity_jaccard_tokens(a, b) > 0.2


def test_tokenize_for_match_drops_short() -> None:
    toks = tokenize_for_match("ab cd efgh")
    assert "ab" not in toks
    assert "efgh" in toks


def test_jaccard_similarity_sets() -> None:
    assert jaccard_similarity_sets({"a", "b", "c"}, {"a", "b", "c"}) == 1.0
    assert jaccard_similarity_sets({"a"}, {"b"}) == 0.0


def test_transliterate_ru_to_latin() -> None:
    assert "lamp" in transliterate_ru_to_latin("лампа")
