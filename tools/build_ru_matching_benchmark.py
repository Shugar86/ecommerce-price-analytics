"""
Build a labelled RU product matching benchmark from ``normalized_offers``.

The output is intended for VKR slides:

* pairs.csv: labelled pairs from live RU supplier feeds;
* metrics.csv: precision/recall/F1 by threshold;
* summary.json: compact headline numbers;
* PNG plots and top_examples.csv for presentation.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.ru_matching_benchmark import (
    build_ru_matching_pairs,
    load_offers_for_benchmark,
    render_benchmark_plots,
    source_names_from_env,
    threshold_sweep,
    write_metrics_csv,
    write_pairs_csv,
    write_summary_json,
    write_top_examples,
)
from app.database import get_engine, get_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


DEFAULT_SOURCES = (
    "TDM Electric,"
    "EKF YML,"
    "IEK (Комплект-Сервис),"
    "EKF (Комплект-Сервис),"
    "Schneider Electric (КС),"
    "Legrand (Комплект-Сервис),"
    "WAGO (Комплект-Сервис),"
    "Syperopt XLSX,"
    "carreta_nsk_opt,"
    "carreta_nsk_retail"
)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/ru_benchmark"),
        help="Output directory for CSV, JSON and PNG files.",
    )
    parser.add_argument(
        "--sources",
        default=os.getenv("RU_BENCHMARK_SOURCES", DEFAULT_SOURCES),
        help="Comma-separated source names. Empty string means all DB sources.",
    )
    parser.add_argument(
        "--per-source-limit",
        type=int,
        default=int(os.getenv("RU_BENCHMARK_PER_SOURCE_LIMIT", "3000")),
        help="Maximum offers loaded per source.",
    )
    parser.add_argument(
        "--max-positive-pairs",
        type=int,
        default=int(os.getenv("RU_BENCHMARK_MAX_POSITIVE_PAIRS", "2500")),
        help="Maximum positive labelled pairs.",
    )
    parser.add_argument(
        "--max-negative-pairs",
        type=int,
        default=int(os.getenv("RU_BENCHMARK_MAX_NEGATIVE_PAIRS", "2500")),
        help="Maximum hard negative labelled pairs.",
    )
    args = parser.parse_args()

    sources = source_names_from_env(args.sources)
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        offers = load_offers_for_benchmark(
            session,
            sources=sources,
            per_source_limit=args.per_source_limit,
        )
    finally:
        session.close()

    logger.info("Loaded benchmark offers: %s", len(offers))
    pairs = build_ru_matching_pairs(
        offers,
        max_positive_pairs=args.max_positive_pairs,
        max_negative_pairs=args.max_negative_pairs,
    )
    metrics = threshold_sweep(pairs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_pairs_csv(args.out_dir / "pairs.csv", pairs)
    write_metrics_csv(args.out_dir / "metrics.csv", metrics)
    summary = write_summary_json(
        args.out_dir / "summary.json",
        pairs=pairs,
        metrics=metrics,
        sources=sources,
    )
    write_top_examples(args.out_dir / "top_examples.csv", pairs)
    created = render_benchmark_plots(args.out_dir, pairs, metrics)

    logger.info("Pairs: %s", len(pairs))
    logger.info("Best F1: %s", summary.get("best_f1"))
    for path in created:
        logger.info("Created plot: %s", path)


if __name__ == "__main__":
    main()
