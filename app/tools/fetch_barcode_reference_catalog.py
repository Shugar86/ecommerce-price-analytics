"""
Скачивание ZIP Catalog.app (Tier B) и загрузка CSV в ``barcode_reference``.

Использование:

    CATALOG_APP_BARCODES_ZIP_URL=... python -m app.tools.fetch_barcode_reference_catalog

Или задать ``BARCODE_REFERENCE_CSV`` после ручного скачивания — ``load_barcode_reference``.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import zipfile
from pathlib import Path

import requests

from app.database import get_engine, get_session, init_db
from app.tools.load_barcode_reference import load_csv

logger = logging.getLogger(__name__)

_DEFAULT_ZIP = (
    "https://catalog.app/public-opportunities/download-public-file"
    "?fileName=barcodes_csv.zip"
)


def _find_csv_in_zip(data: bytes) -> tuple[str, bytes]:
    """Первый крупный CSV внутри ZIP (имя, содержимое)."""
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("no CSV in zip")
        # Берём самый большой csv (основной дамп)
        best = max(names, key=lambda n: zf.getinfo(n).file_size)
        with zf.open(best) as f:
            return best, f.read()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Download Catalog.app barcodes zip and load barcode_reference"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CATALOG_APP_BARCODES_ZIP_URL", _DEFAULT_ZIP),
        help="URL zip (default Catalog.app public)",
    )
    parser.add_argument(
        "--batch",
        default=os.environ.get("BARCODE_REFERENCE_BATCH", "catalog_app_zip"),
        help="source_batch",
    )
    args = parser.parse_args()
    if not args.url:
        print("Set --url or CATALOG_APP_BARCODES_ZIP_URL", file=sys.stderr)
        sys.exit(2)
    logger.info("Скачивание %s", args.url)
    r = requests.get(
        args.url,
        timeout=(20, 600),
        headers={"User-Agent": "PriceDesk-Tool/1.0"},
    )
    r.raise_for_status()
    name, content = _find_csv_in_zip(r.content)
    logger.info("Распакован CSV: %s (%s bytes)", name, len(content))
    work = Path("/tmp") / f"barcode_ref_{os.getpid()}.csv"
    work.write_bytes(content)
    try:
        engine = get_engine()
        init_db(engine)
        session = get_session(engine)
        try:
            n = load_csv(session, work, batch=str(args.batch))
            print(f"Loaded {n} barcode rows from Catalog.app zip", file=sys.stderr)
        finally:
            session.close()
    finally:
        if work.is_file():
            work.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
