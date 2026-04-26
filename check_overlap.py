"""Check overlap between TBM Market and GalaCentre YML feeds by barcode.

This script is meant to be run inside the project Docker container (collector),
where Python dependencies (requests, lxml) are available.

It downloads both YML feeds, streams through <offer> entries, extracts barcodes,
and reports intersections. It stops early once enough matches are found.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Optional

import requests
from lxml import etree


TBM_URL = "https://www.tbmmarket.ru/tbmmarket/service/yandex-market.xml"
GALA_URL = "https://www.galacentre.ru/download/yml/yml.xml"

KEYWORDS = [
    "микроволнов",
    "свч",
    "холодиль",
    "морозиль",
    "чайник",
    "термос",
]


_BARCODE_RE = re.compile(r"\d{8,14}")


@dataclass(frozen=True)
class FeedStats:
    """Stats collected from a feed scan."""

    offers_seen: int
    barcodes_seen: int
    unique_barcodes: int


def _extract_barcodes(raw: Optional[str]) -> list[str]:
    """Extract normalized barcodes from raw text.

    Args:
        raw: Raw barcode text from XML. Can contain commas and other characters.

    Returns:
        List of digit-only barcodes (8..14 digits), de-duplicated, preserving order.
    """
    if not raw:
        return []

    found = _BARCODE_RE.findall(raw)
    if not found:
        return []

    # De-dup preserve order
    seen: set[str] = set()
    out: list[str] = []
    for bc in found:
        if bc not in seen:
            seen.add(bc)
            out.append(bc)
    return out


def _iter_offer_barcodes(url: str, *, offer_limit: int) -> tuple[set[str], FeedStats]:
    """Stream offers from YML and collect barcodes.

    Args:
        url: YML feed URL.
        offer_limit: Max <offer> elements to scan.

    Returns:
        (set_of_barcodes, stats)
    """
    try:
        resp = requests.get(url, stream=True, timeout=(10, 180))
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download feed: {url}. Error: {e}") from e

    offers_seen = 0
    barcodes_seen = 0
    barcodes: set[str] = set()

    # Stream XML parsing to avoid loading huge feeds into memory.
    resp.raw.decode_content = True
    try:
        context = etree.iterparse(
            resp.raw,
            events=("end",),
            tag="offer",
            recover=True,
            huge_tree=True,
        )
    except (etree.XMLSyntaxError, ValueError) as e:
        raise RuntimeError(f"Failed to initialize XML iterparse for {url}: {e}") from e

    for _, offer in context:
        offers_seen += 1
        # name keyword stats (best-effort)
        _ = offer.findtext("name")  # touch element to keep parse consistent
        raw_bc = offer.findtext("barcode")
        for bc in _extract_barcodes(raw_bc):
            barcodes_seen += 1
            barcodes.add(bc)

        offer.clear()
        while offer.getprevious() is not None:
            del offer.getparent()[0]

        if offers_seen >= offer_limit:
            break

    del context
    return barcodes, FeedStats(
        offers_seen=offers_seen,
        barcodes_seen=barcodes_seen,
        unique_barcodes=len(barcodes),
    )


def _count_keyword_hits(url: str, *, offer_limit: int) -> dict[str, int]:
    """Count how many offers match each keyword (substring match on <name>)."""
    resp = requests.get(url, stream=True, timeout=(10, 180))
    resp.raise_for_status()
    resp.raw.decode_content = True

    hits = {k: 0 for k in KEYWORDS}
    seen = 0
    context = etree.iterparse(
        resp.raw,
        events=("end",),
        tag="offer",
        recover=True,
        huge_tree=True,
    )

    for _, offer in context:
        seen += 1
        name = (offer.findtext("name") or "").lower()
        for k in KEYWORDS:
            if k in name:
                hits[k] += 1

        offer.clear()
        while offer.getprevious() is not None:
            del offer.getparent()[0]

        if seen >= offer_limit:
            break

    del context
    return hits


def main() -> None:
    """Entry point."""
    # Progressive scan until we find overlap or hit max.
    steps = [2_000, 10_000, 50_000, 150_000]
    need_matches = 10

    for limit in steps:
        print(f"\n== Scanning up to {limit:,} offers from each feed ==")

        tbm_barcodes, tbm_stats = _iter_offer_barcodes(TBM_URL, offer_limit=limit)
        print(f"TBM: offers={tbm_stats.offers_seen:,}, unique_barcodes={tbm_stats.unique_barcodes:,}")

        gala_barcodes, gala_stats = _iter_offer_barcodes(GALA_URL, offer_limit=limit)
        print(f"GALA: offers={gala_stats.offers_seen:,}, unique_barcodes={gala_stats.unique_barcodes:,}")

        overlap = tbm_barcodes.intersection(gala_barcodes)
        print(f"OVERLAP(barcode): {len(overlap):,}")

        if overlap:
            sample = list(sorted(overlap))[:need_matches]
            print("Sample barcodes:")
            for bc in sample:
                print(f"- {bc}")
            if len(overlap) >= need_matches:
                break

    print("\nDone.")

    print("\n== Keyword presence scan (names) ==")
    limit = 50_000
    tbm_hits = _count_keyword_hits(TBM_URL, offer_limit=limit)
    gala_hits = _count_keyword_hits(GALA_URL, offer_limit=limit)
    print(f"TBM hits (limit {limit:,} offers): {tbm_hits}")
    print(f"GALA hits (limit {limit:,} offers): {gala_hits}")


if __name__ == "__main__":
    main()


