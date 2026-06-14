"""Tests for RU matching benchmark generation."""

from __future__ import annotations

from pathlib import Path

from app.analytics.ru_matching_benchmark import (
    BenchmarkOffer,
    best_f1,
    build_ru_matching_pairs,
    metrics_at_threshold,
    read_pairs_csv,
    render_benchmark_plots,
    threshold_sweep,
    write_pairs_csv,
    write_top_examples,
)


def _offer(
    idx: int,
    source: str,
    name: str,
    brand: str,
    vendor: str,
    price: float,
) -> BenchmarkOffer:
    return BenchmarkOffer(
        id=idx,
        source_name=source,
        name=name,
        brand=brand.upper(),
        vendor_code=vendor.upper(),
        barcode="",
        category="",
        price_rub=price,
    )


def test_build_ru_matching_pairs_has_positive_and_hard_negative() -> None:
    """Exact vendor+brand creates label=1; same brand/different code creates label=0."""
    offers = [
        _offer(1, "TDM Electric", "Клемма WAGO 221-412 2-проводная", "WAGO", "221-412", 100),
        _offer(2, "Syperopt XLSX", "Соединительная клемма WAGO 221-412", "WAGO", "221-412", 118),
        _offer(3, "TDM Electric", "Клемма WAGO 221-413 3-проводная", "WAGO", "221-413", 120),
        _offer(4, "Syperopt XLSX", "Соединительная клемма WAGO 221-413", "WAGO", "221-413", 130),
    ]
    pairs = build_ru_matching_pairs(
        offers,
        max_positive_pairs=10,
        max_negative_pairs=10,
        comparisons_per_brand=50,
    )
    assert any(p.label == 1 and p.label_source == "exact_vendor_brand" for p in pairs)
    assert any(p.label == 0 and p.label_source.startswith("hard_negative") for p in pairs)
    assert all(p.left_source != p.right_source for p in pairs)


def test_metrics_and_best_f1() -> None:
    """Threshold metrics are computed without sklearn dependency."""
    offers = [
        _offer(1, "A", "Автомат IEK 16А", "IEK", "BA47-16", 100),
        _offer(2, "B", "Выключатель автоматический IEK 16A", "IEK", "BA47-16", 110),
        _offer(3, "A", "Автомат IEK 25А", "IEK", "BA47-25", 105),
        _offer(4, "B", "Выключатель автоматический IEK 25A", "IEK", "BA47-25", 115),
    ]
    pairs = build_ru_matching_pairs(offers, max_positive_pairs=10, max_negative_pairs=10)
    m = metrics_at_threshold(pairs, 0.0)
    assert m.total == len(pairs)
    assert m.positives > 0
    sweep = threshold_sweep(pairs, step=0.25)
    assert best_f1(sweep).f1 >= 0.0


def test_write_read_pairs_and_render_plots(tmp_path: Path) -> None:
    """CSV/PNG artifacts can be created for slides."""
    offers = [
        _offer(1, "A", "Помпа водяная HYUNDAI 25100-45003", "HYUNDAI", "25100-45003", 6800),
        _offer(2, "B", "Помпа водяная 25100-45003 Hyundai", "HYUNDAI", "25100-45003", 8250),
        _offer(3, "A", "Помпа водяная HYUNDAI 25100-45004", "HYUNDAI", "25100-45004", 6900),
        _offer(4, "B", "Помпа водяная 25100-45004 Hyundai", "HYUNDAI", "25100-45004", 8350),
    ]
    pairs = build_ru_matching_pairs(offers, max_positive_pairs=10, max_negative_pairs=10)
    csv_path = tmp_path / "pairs.csv"
    write_pairs_csv(csv_path, pairs)
    assert len(read_pairs_csv(csv_path)) == len(pairs)
    metrics = threshold_sweep(pairs, step=0.5)
    created = render_benchmark_plots(tmp_path, pairs, metrics)
    write_top_examples(tmp_path / "top_examples.csv", pairs, limit=2)
    assert (tmp_path / "top_examples.csv").is_file()
    assert {Path(p).suffix for p in created} == {".png"}
