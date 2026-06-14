"""Тесты offline-генерации графиков для ВКР."""

from __future__ import annotations

from pathlib import Path

from app.analytics.defense_visuals import (
    load_manifest,
    load_offers_csv,
    render_defense_assets,
)


def test_load_fixture_offers_csv() -> None:
    """Фикстура читается в список словарей с числовой ценой."""
    root = Path(__file__).resolve().parents[1]
    path = root / "tests/fixtures/demo_defense/offers.csv"
    rows = load_offers_csv(path)
    assert len(rows) == 4
    assert rows[0]["price_rub"] == 450.50


def test_render_defense_creates_png_and_top_matches(tmp_path: Path) -> None:
    """Генерация артефактов не падает и создаёт ожидаемые файлы."""
    root = Path(__file__).resolve().parents[1]
    demo_dir = root / "tests/fixtures/demo_defense"
    manifest = load_manifest(demo_dir / "manifest.json")
    offers = load_offers_csv(demo_dir / "offers.csv")
    paths = render_defense_assets(manifest, offers, tmp_path)
    suffixes = {Path(p).name for p in paths}
    assert "source_coverage.png" in suffixes
    assert "match_score_distribution.png" in suffixes
    assert "price_gap_by_source.png" in suffixes
    assert "demo_funnel.png" in suffixes
    assert "top_matches.csv" in suffixes
    csv_path = tmp_path / "top_matches.csv"
    assert csv_path.is_file()
    text = csv_path.read_text(encoding="utf-8")
    assert "vendor_code" in text
