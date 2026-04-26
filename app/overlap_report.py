"""
Generate a practical overlap report between shops in DB.

Focus:
- exact overlaps by barcode
- exact overlaps by vendor_code
- exact overlaps by name_norm (normalized name)

Run inside docker:
  docker-compose exec -T collector python -m app.overlap_report > OVERLAPS_REPORT.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import combinations
import re
from typing import Iterable, Optional

from sqlalchemy import select

from app.database import Product, get_engine, get_session, init_db
from app.matching.text import jaccard_similarity_sets, transliterate_ru_to_latin


@dataclass(frozen=True)
class ShopStats:
    total: int
    with_barcode: int
    with_vendor_code: int
    with_name_norm: int


_STOPWORDS = {
    # RU
    "и", "или", "в", "во", "на", "для", "по", "от", "до", "к", "ко", "с", "со", "без",
    "не", "это", "а", "но", "при", "над", "под", "за", "у", "из", "как", "что",
    # Common "trash" units/markers
    "шт", "уп", "упак", "компл", "мм", "см", "м", "кг", "г", "л", "мл", "pcs", "pc",
    # EN common
    "the", "and", "or", "for", "with", "without", "in", "on", "of", "to",

    # Common vendor/format noise across feeds
    "ekf", "tdm", "ng", "by", "pk", "pt",
}

_ALNUM_LAT_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_ALNUM_MIX_LAT_RE = re.compile(r"(?=.*[a-z])(?=.*\d)[a-z0-9]+", re.IGNORECASE)


def _tokens(name_norm: str) -> set[str]:
    """
    Tokenize for cross-shop matching.
    Important: we compare in *latin* space, because EKF uses latin slugs, while many RU shops use Cyrillic.
    """
    lat = transliterate_ru_to_latin(name_norm)
    parts = _ALNUM_LAT_RE.findall(lat)
    out = {p for p in parts if len(p) >= 3 and p not in _STOPWORDS}
    return out


def _informative_tokens(tokens: set[str]) -> set[str]:
    """Tokens that likely represent meaning (not just numbers)."""
    out = set()
    for t in tokens:
        if t.isdigit():
            continue
        if t.startswith("ip") and t[2:].isdigit():
            # IP ratings are useful as filters, but terrible as identity keys.
            continue
        # must include at least one letter
        if any("a" <= ch <= "z" for ch in t) and len(t) >= 5:
            out.add(t)
    return out


def _anchor_token(tokens: set[str]) -> Optional[str]:
    """Pick a blocking token that is likely to be specific."""
    if not tokens:
        return None
    # Prefer alnum-mixed (letters+digits), then long tokens.
    mixed = sorted([t for t in tokens if _ALNUM_MIX_LAT_RE.fullmatch(t)], key=len, reverse=True)
    if mixed:
        return mixed[0]
    longish = sorted([t for t in tokens if len(t) >= 8], key=len, reverse=True)
    if longish:
        return longish[0]
    return sorted(tokens, key=len, reverse=True)[0]


def _fetch_name_rows(session, shop: str, limit: int) -> list[tuple[str, str]]:
    """Return list of (name_norm, name) for fuzzy matching."""
    # Prefer name_norm (already normalized); fallback to empty string filtered out later.
    rows = session.execute(
        select(Product.name_norm, Product.name)
        .where(Product.source_shop == shop, Product.name_norm.is_not(None))
        .limit(limit)
    ).all()
    out = []
    for nn, n in rows:
        if nn and n:
            out.append((nn, n))
    return out


def _fuzzy_overlaps(
    rows_a: list[tuple[str, str]],
    rows_b: list[tuple[str, str]],
    *,
    threshold: float,
    max_examples: int,
) -> tuple[int, list[tuple[float, str, str]]]:
    """
    Returns (match_count, examples) where examples are (score, name_a, name_b).
    Uses blocking by an anchor token to keep it fast.
    """
    def blocking_tokens(toks: set[str]) -> list[str]:
        # Use more permissive blocking: digits, mixed, and long tokens.
        out = []
        for t in toks:
            if _ALNUM_MIX_LAT_RE.fullmatch(t):
                out.append(t)
            elif len(t) >= 8:
                out.append(t)
            elif any(ch.isdigit() for ch in t) and len(t) >= 4:
                # digits-only tokens are too noisy; only keep longer numeric-ish tokens late
                out.append(t)
        if not out:
            # fallback to a single anchor
            a = _anchor_token(toks)
            if a:
                out = [a]
        # limit number of blocking tokens to keep candidate sets sane
        out = sorted(set(out), key=len, reverse=True)[:6]
        return out

    # Inverted index B by blocking tokens
    index: dict[str, list[tuple[set[str], str]]] = {}
    for nn, name in rows_b:
        tb = _tokens(nn)
        for bt in blocking_tokens(tb):
            bucket = index.setdefault(bt, [])
            # cap per bucket to prevent huge candidate lists
            if len(bucket) < 250:
                bucket.append((tb, name))

    matched = 0
    examples: list[tuple[float, str, str]] = []
    for nn_a, name_a in rows_a:
        ta = _tokens(nn_a)
        ita = _informative_tokens(ta)
        bts = blocking_tokens(ta)
        if not bts:
            continue
        cand: list[tuple[set[str], str]] = []
        seen = 0
        for bt in bts:
            bucket = index.get(bt)
            if not bucket:
                continue
            cand.extend(bucket)
            seen += len(bucket)
            if seen >= 1200:
                break
        if not cand:
            continue
        best_score = 0.0
        best_name_b: Optional[str] = None
        # Cap comparisons per A item
        for tb, name_b in cand[:1200]:
            itb = _informative_tokens(tb)
            # Guardrails: match only when BOTH sides have enough meaningful tokens
            # and share at least 1 of them. Otherwise we get tons of false positives on numbers/codes.
            if not ita or not itb:
                continue
            if len(ita) < 2 or len(itb) < 2:
                continue
            if not (ita & itb):
                continue
            score = jaccard_similarity_sets(ita, itb)
            if score > best_score:
                best_score = score
                best_name_b = name_b
        if best_score >= threshold and best_name_b:
            matched += 1
            if len(examples) < max_examples:
                examples.append((best_score, name_a, best_name_b))

    examples.sort(key=lambda x: x[0], reverse=True)
    return matched, examples[:max_examples]


def _fetch_shops(session) -> list[str]:
    rows = session.execute(select(Product.source_shop).distinct()).all()
    return sorted({r[0] for r in rows if r and r[0]})


def _shop_stats(session, shop: str) -> ShopStats:
    rows = session.execute(
        select(Product.barcode, Product.vendor_code, Product.name_norm).where(Product.source_shop == shop)
    ).all()
    total = len(rows)
    with_barcode = sum(1 for b, _, _ in rows if b)
    with_vendor_code = sum(1 for _, v, _ in rows if v)
    with_name_norm = sum(1 for _, _, n in rows if n)
    return ShopStats(total=total, with_barcode=with_barcode, with_vendor_code=with_vendor_code, with_name_norm=with_name_norm)


def _fetch_keyset(session, shop: str, field: str) -> set[str]:
    col = getattr(Product, field)
    rows = session.execute(select(col).where(Product.source_shop == shop, col.is_not(None))).all()
    return {r[0] for r in rows if r and r[0]}


def _fetch_examples(session, shop_a: str, shop_b: str, field: str, keys: Iterable[str], limit: int = 10) -> list[tuple[str, str, str]]:
    """Return list of (key, name_a, name_b) for a few overlaps."""
    col = getattr(Product, field)
    key_list = list(keys)[:limit]
    if not key_list:
        return []

    a_rows = session.execute(
        select(col, Product.name).where(Product.source_shop == shop_a, col.in_(key_list))
    ).all()
    b_rows = session.execute(
        select(col, Product.name).where(Product.source_shop == shop_b, col.in_(key_list))
    ).all()

    a_map: dict[str, str] = {}
    for k, n in a_rows:
        if k and n and k not in a_map:
            a_map[k] = n
    b_map: dict[str, str] = {}
    for k, n in b_rows:
        if k and n and k not in b_map:
            b_map[k] = n

    out: list[tuple[str, str, str]] = []
    for k in key_list:
        if k in a_map and k in b_map:
            out.append((k, a_map[k], b_map[k]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=10)
    ap.add_argument("--fuzzy-limit", type=int, default=5000, help="Max rows per shop for fuzzy matching (per pair).")
    ap.add_argument("--fuzzy-threshold", type=float, default=0.72, help="Jaccard token similarity threshold.")
    args = ap.parse_args()

    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        shops = _fetch_shops(session)
        print("## Shops loaded\n")
        for s in shops:
            st = _shop_stats(session, s)
            print(f"- **{s}**: total={st.total}, barcode={st.with_barcode}, vendor_code={st.with_vendor_code}, name_norm={st.with_name_norm}")

        print("\n## Overlaps (exact)\n")

        # Preload sets for speed
        sets: dict[tuple[str, str], set[str]] = {}
        for s in shops:
            for field in ("barcode", "vendor_code", "name_norm"):
                sets[(s, field)] = _fetch_keyset(session, s, field)

        for a, b in combinations(shops, 2):
            print(f"### {a} ↔ {b}\n")
            for field, label in (("barcode", "barcode"), ("vendor_code", "vendor_code"), ("name_norm", "name_norm")):
                inter = sets[(a, field)].intersection(sets[(b, field)])
                print(f"- **{label} overlap**: {len(inter)}")
                if inter:
                    examples = _fetch_examples(session, a, b, field, sorted(inter), limit=args.examples)
                    if examples:
                        print(f"  - **examples ({len(examples)})**:")
                        for k, na, nb in examples:
                            k_disp = str(k)[:80]
                            na_disp = (na or '')[:140]
                            nb_disp = (nb or '')[:140]
                            print(f"    - `{k_disp}` | {na_disp}  ↔  {nb_disp}")
            print()

        print("## Overlaps (fuzzy name match)\n")
        print(
            f"Settings: limit_per_shop={args.fuzzy_limit}, threshold={args.fuzzy_threshold:.2f}. "
            "This is heuristic matching (expected when barcodes/vendor codes do not overlap).\n"
        )

        for a, b in combinations(shops, 2):
            rows_a = _fetch_name_rows(session, a, args.fuzzy_limit)
            rows_b = _fetch_name_rows(session, b, args.fuzzy_limit)
            count, examples = _fuzzy_overlaps(
                rows_a,
                rows_b,
                threshold=args.fuzzy_threshold,
                max_examples=args.examples,
            )
            print(f"### {a} ≈ {b}\n")
            print(f"- **fuzzy name matches**: {count}")
            if examples:
                print(f"  - **examples ({len(examples)})**:")
                for score, na, nb in examples:
                    na_disp = (na or "")[:160]
                    nb_disp = (nb or "")[:160]
                    print(f"    - **{score:.2f}** | {na_disp}  ↔  {nb_disp}")
            print()

        # Quick "leaderboard" for name_norm overlaps
        print("## Top overlaps by name_norm\n")
        leaderboard = []
        for a, b in combinations(shops, 2):
            n = len(sets[(a, "name_norm")].intersection(sets[(b, "name_norm")]))
            leaderboard.append((n, a, b))
        leaderboard.sort(reverse=True)
        for n, a, b in leaderboard[:15]:
            print(f"- **{a} ↔ {b}**: {n}")

    finally:
        session.close()


if __name__ == "__main__":
    main()


