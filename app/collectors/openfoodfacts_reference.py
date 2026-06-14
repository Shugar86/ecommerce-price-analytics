"""Open Food Facts reference catalog connector.

Open Food Facts is used only as an open barcode/catalog reference source. It does
not publish prices, so rows from this connector enrich ``barcode_reference`` and
must not be treated as market offers.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app.database import BarcodeReference, get_engine, get_session, init_db
from app.ml.matching import normalize_barcode

logger = logging.getLogger(__name__)

OPENFOODFACTS_SEARCH_URL = "https://world.openfoodfacts.org/api/v2/search"
DEFAULT_COUNTRY_TAG = "en:russian-federation"
DEFAULT_PAGE_SIZE = 50
DEFAULT_USER_AGENT = "PriceDesk-OpenFoodFactsConnector/1.0 (local-vkr-audit)"
OPENFOODFACTS_FIELDS = (
    "code,product_name,product_name_ru,generic_name,brands,categories,"
    "categories_tags,quantity,url,countries_tags"
)

ReferenceRow = dict[str, str | None]


def _clean_text(value: object) -> str | None:
    """Return a compact non-empty string or ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return " ".join(text.split()) if text else None


def _first_csv_value(value: object) -> str | None:
    """Return the first non-empty comma-separated value."""
    text = _clean_text(value)
    if not text:
        return None
    for part in text.split(","):
        cleaned = _clean_text(part)
        if cleaned:
            return cleaned
    return None


def _first_tag_value(value: object) -> str | None:
    """Return a readable value from a tag list such as ``en:biscuits``."""
    if not isinstance(value, list):
        return None
    for item in value:
        text = _clean_text(item)
        if not text:
            continue
        return text.split(":", 1)[-1].replace("-", " ")
    return None


def normalize_openfoodfacts_product(product: Mapping[str, Any]) -> ReferenceRow | None:
    """Normalize one Open Food Facts product into ``barcode_reference`` fields.

    Args:
        product: Raw product object returned by the Open Food Facts API.

    Returns:
        A row compatible with ``barcode_reference`` or ``None`` when the product
        has no valid barcode or useful display name.
    """
    barcode = normalize_barcode(_clean_text(product.get("code")))
    if not barcode or len(barcode) < 8:
        return None

    name = (
        _clean_text(product.get("product_name_ru"))
        or _clean_text(product.get("product_name"))
        or _clean_text(product.get("generic_name"))
    )
    if not name:
        return None

    category = _first_csv_value(product.get("categories")) or _first_tag_value(
        product.get("categories_tags")
    )
    return {
        "barcode": barcode,
        "article": None,
        "vendor": _first_csv_value(product.get("brands")),
        "name": name[:500],
        "category": category[:500] if category else None,
    }


def fetch_openfoodfacts_reference_rows(
    *,
    country_tag: str = DEFAULT_COUNTRY_TAG,
    page_size: int = DEFAULT_PAGE_SIZE,
    http_session: requests.Session | None = None,
) -> list[ReferenceRow]:
    """Fetch and normalize a small Open Food Facts country-filtered page.

    Args:
        country_tag: Open Food Facts country tag, e.g. ``en:russian-federation``.
        page_size: Number of products to request from the public API.
        http_session: Optional requests session for tests or caller-managed HTTP.

    Returns:
        Normalized rows suitable for ``barcode_reference``.

    Raises:
        ValueError: If the API returns an unexpected JSON shape.
        requests.RequestException: If the public API request fails.
    """
    params = {
        "countries_tags": country_tag,
        "fields": OPENFOODFACTS_FIELDS,
        "page_size": max(1, min(page_size, 1000)),
        "json": 1,
    }
    headers = {"User-Agent": os.getenv("OPENFOODFACTS_USER_AGENT", DEFAULT_USER_AGENT)}
    client = http_session or requests.Session()
    try:
        response = client.get(
            OPENFOODFACTS_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=(10, 45),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.error("OpenFoodFacts: HTTP error: %s", exc)
        raise
    except ValueError as exc:
        logger.error("OpenFoodFacts: invalid JSON: %s", exc)
        raise

    products = payload.get("products") if isinstance(payload, Mapping) else None
    if not isinstance(products, list):
        raise ValueError("OpenFoodFacts response does not contain products list")

    rows: list[ReferenceRow] = []
    for product in products:
        if not isinstance(product, Mapping):
            continue
        row = normalize_openfoodfacts_product(product)
        if row is not None:
            rows.append(row)
    return rows


def _sqlite_upsert_one(
    session: DbSession,
    row: ReferenceRow,
    *,
    batch_label: str,
) -> None:
    barcode = row["barcode"]
    if barcode is None:
        return
    existing = session.execute(
        select(BarcodeReference).where(BarcodeReference.barcode == barcode)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            BarcodeReference(
                barcode=barcode,
                article=row.get("article"),
                vendor=row.get("vendor"),
                name=row.get("name"),
                category=row.get("category"),
                source_batch=batch_label,
            )
        )
        return
    if row.get("article"):
        existing.article = row["article"]
    if row.get("vendor"):
        existing.vendor = row["vendor"]
    if row.get("name"):
        existing.name = row["name"]
    if row.get("category"):
        existing.category = row["category"]
    existing.source_batch = batch_label


def _upsert_reference_rows(
    session: DbSession,
    rows: list[ReferenceRow],
    *,
    batch_label: str,
) -> int:
    """Upsert normalized Open Food Facts rows into ``barcode_reference``."""
    if not rows:
        return 0
    bind = session.get_bind()
    use_pg = bind is not None and bind.dialect.name == "postgresql"
    batch = batch_label[:64]
    values = [
        {
            "barcode": row["barcode"],
            "article": row.get("article"),
            "vendor": row.get("vendor"),
            "name": row.get("name"),
            "category": row.get("category"),
            "source_batch": batch,
        }
        for row in rows
        if row.get("barcode")
    ]
    if not values:
        return 0
    if use_pg:
        stmt = pg_insert(BarcodeReference).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[BarcodeReference.barcode],
            set_={
                "article": func.coalesce(
                    stmt.excluded.article, BarcodeReference.article
                ),
                "vendor": func.coalesce(stmt.excluded.vendor, BarcodeReference.vendor),
                "name": func.coalesce(stmt.excluded.name, BarcodeReference.name),
                "category": func.coalesce(
                    stmt.excluded.category, BarcodeReference.category
                ),
                "source_batch": stmt.excluded.source_batch,
            },
        )
        session.execute(stmt)
    else:
        for row in rows:
            _sqlite_upsert_one(session, row, batch_label=batch)
    return len(values)


def load_openfoodfacts_reference(
    session: DbSession,
    *,
    country_tag: str = DEFAULT_COUNTRY_TAG,
    page_size: int = DEFAULT_PAGE_SIZE,
    batch_label: str | None = None,
) -> int:
    """Fetch Open Food Facts rows and load them into ``barcode_reference``.

    Args:
        session: SQLAlchemy session.
        country_tag: Open Food Facts country tag.
        page_size: Number of API products to request.
        batch_label: Optional source batch label.

    Returns:
        Number of rows inserted or updated. Returns ``0`` on logged IO/DB errors.
    """
    try:
        rows = fetch_openfoodfacts_reference_rows(
            country_tag=country_tag,
            page_size=page_size,
        )
        loaded = _upsert_reference_rows(
            session,
            rows,
            batch_label=batch_label or f"openfoodfacts_{country_tag}",
        )
        session.commit()
        logger.info("OpenFoodFacts: loaded %s reference rows", loaded)
        return loaded
    except (requests.RequestException, ValueError, SQLAlchemyError) as exc:
        logger.error("OpenFoodFacts: load failed: %s", exc)
        session.rollback()
        return 0


def write_openfoodfacts_sample(
    path: Path,
    *,
    country_tag: str = DEFAULT_COUNTRY_TAG,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> int:
    """Write a small reproducible Open Food Facts JSON sample.

    Args:
        path: Destination JSON file.
        country_tag: Open Food Facts country tag.
        page_size: Number of API products to request.

    Returns:
        Number of normalized rows written.

    Raises:
        OSError: If the sample file cannot be written.
        requests.RequestException: If the public API request fails.
        ValueError: If the API response is malformed.
    """
    rows = fetch_openfoodfacts_reference_rows(
        country_tag=country_tag,
        page_size=page_size,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "source_url": OPENFOODFACTS_SEARCH_URL,
                    "country_tag": country_tag,
                    "page_size": page_size,
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("OpenFoodFacts: cannot write sample %s: %s", path, exc)
        raise
    return len(rows)


def main() -> None:
    """CLI for downloading a small sample or loading ``barcode_reference``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Fetch Open Food Facts reference catalog rows"
    )
    parser.add_argument("--country-tag", default=DEFAULT_COUNTRY_TAG)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--sample-out", default="")
    parser.add_argument("--load-db", action="store_true")
    args = parser.parse_args()

    if args.sample_out:
        count = write_openfoodfacts_sample(
            Path(args.sample_out),
            country_tag=str(args.country_tag),
            page_size=int(args.page_size),
        )
        print(f"Wrote {count} Open Food Facts reference rows")

    if args.load_db:
        engine = get_engine()
        init_db(engine)
        session = get_session(engine)
        try:
            count = load_openfoodfacts_reference(
                session,
                country_tag=str(args.country_tag),
                page_size=int(args.page_size),
            )
            print(f"Loaded {count} Open Food Facts reference rows")
        finally:
            session.close()


if __name__ == "__main__":
    main()
