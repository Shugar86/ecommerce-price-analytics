"""
CLI: строит PNG и top_matches.csv из ``artifacts/demo`` в ``artifacts/defense``.

Запуск из корня репозитория::

    python tools/build_defense_visuals.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.defense_visuals import build_from_demo_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Парсит аргументы и вызывает построение графиков."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=Path("artifacts/demo"),
        help="Каталог с manifest.json и offers.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/defense"),
        help="Куда сохранить PNG и CSV",
    )
    args = parser.parse_args()
    paths = build_from_demo_dir(args.demo_dir, args.out_dir)
    for p in paths:
        logger.info("Создан файл: %s", p)


if __name__ == "__main__":
    main()
