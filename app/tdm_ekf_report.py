"""
TDM ↔ EKF matching report (names only).

We ignore barcodes/vendor codes completely and match purely by names, but with:
- aggressive normalization (ru->latin translit + punctuation cleanup)
- token extraction focused on "model/series" tokens (letters+digits)
- blocking index to avoid O(N^2)
- weighted Jaccard (IDF) on informative tokens

Run:
  docker-compose exec -T collector python -m app.tdm_ekf_report > TDM_EKF_REPORT.md
"""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select

from app.database import Product, get_engine, get_session, init_db


# --- Normalization / transliteration ---

_RU_TO_LAT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ы": "y",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "ь": "",
        "ъ": "",
    }
)

_ALNUM = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_MODEL_TOKEN = re.compile(r"(?=.*[a-z])(?=.*\d)[a-z0-9][a-z0-9\\-_/\\.]{2,32}$", re.IGNORECASE)

_STOP = {
    # RU stop-ish
    "dlya",
    "bez",
    "na",
    "v",
    "po",
    "s",
    "do",
    "ot",
    # Brands/shops often present in slugs
    "ekf",
    "tdm",
    # Units/ratings
    "mm",
    "sm",
    "m",
    "kg",
    "g",
    "l",
    "ml",
    "vt",
    "w",
    "a",
    "kv",
    "ip",
    "ip54",
    "ip65",
    "ip67",
    "ral",
}


def _to_latin(s: str) -> str:
    s = s.lower().replace("ё", "е")
    out = []
    for ch in s:
        if "а" <= ch <= "я" or ch in ("ё", "ь", "ъ"):
            out.append(_RU_TO_LAT.get(ch, ""))  # type: ignore[arg-type]
        else:
            out.append(ch)
    return "".join(out)


def _normalize(s: str) -> str:
    s = _to_latin(s)
    # unify separators
    s = (
        s.replace("×", "x")
        .replace("/", " ")
        .replace("\\\\", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("[", " ")
        .replace("]", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("|", " ")
        .replace("+", " ")
        .replace("—", " ")
        .replace("–", " ")
        .replace("-", " ")
        .replace("'", " ")
        .replace("\"", " ")
    )
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def _tokens(norm: str) -> list[str]:
    toks = [t for t in _ALNUM.findall(norm) if len(t) >= 3]
    toks = [t for t in toks if t not in _STOP]
    return toks


def _model_tokens(toks: Iterable[str]) -> set[str]:
    out = set()
    for t in toks:
        if _MODEL_TOKEN.match(t):
            out.add(t)
    return out


def _word_tokens(toks: Iterable[str]) -> set[str]:
    out = set()
    for t in toks:
        if t.isdigit():
            continue
        # require at least one letter
        if any("a" <= ch <= "z" for ch in t) and len(t) >= 5:
            out.add(t)
    return out


def _idf_weights(docs: list[set[str]]) -> dict[str, float]:
    df = Counter()
    for d in docs:
        for t in d:
            df[t] += 1
    n = max(1, len(docs))
    # smooth idf
    return {t: math.log((n + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}


def _weighted_jaccard(a: set[str], b: set[str], w: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    si = sum(w.get(t, 1.0) for t in inter)
    su = sum(w.get(t, 1.0) for t in union)
    return si / su if su else 0.0


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    norm: str
    toks: list[str]
    models: set[str]
    words: set[str]


def _fetch_items(session, shop: str, limit: int) -> list[Item]:
    rows = session.execute(
        select(Product.id, Product.name)
        .where(Product.source_shop == shop)
        .limit(limit)
    ).all()
    out: list[Item] = []
    for pid, name in rows:
        if not name:
            continue
        norm = _normalize(name)
        toks = _tokens(norm)
        models = _model_tokens(toks)
        words = _word_tokens(toks)
        out.append(Item(id=int(pid), name=str(name), norm=norm, toks=toks, models=models, words=words))
    return out


def _block_keys(item: Item) -> list[str]:
    # Prefer model tokens (best anchors), else long word tokens
    if item.models:
        return sorted(item.models)[:6]
    # long words as secondary anchors
    long_words = sorted([w for w in item.words if len(w) >= 8], key=len, reverse=True)
    return long_words[:4]


def _match_report(
    a_items: list[Item],
    b_items: list[Item],
    *,
    threshold: float,
    max_examples: int,
) -> tuple[int, list[tuple[float, str, str]]]:
    # Build docs for IDF from union of informative tokens
    docs = [it.models | it.words for it in (a_items + b_items) if (it.models or it.words)]
    w = _idf_weights(docs)

    # Inverted index for B by blocking key
    index: dict[str, list[Item]] = defaultdict(list)
    for it in b_items:
        for k in _block_keys(it):
            if len(index[k]) < 500:
                index[k].append(it)

    matches = 0
    examples: list[tuple[float, str, str]] = []

    for it in a_items:
        keys = _block_keys(it)
        if not keys:
            continue
        cand: list[Item] = []
        seen_ids = set()
        for k in keys:
            for bj in index.get(k, []):
                if bj.id in seen_ids:
                    continue
                seen_ids.add(bj.id)
                cand.append(bj)
            if len(cand) >= 1500:
                break
        if not cand:
            continue

        best_score = 0.0
        best_name: Optional[str] = None
        a_inf = it.models | it.words
        if len(a_inf) < 2:
            continue

        for bj in cand[:1500]:
            b_inf = bj.models | bj.words
            if len(b_inf) < 2:
                continue
            # Guardrail: share at least one model token OR at least 2 word tokens
            if not (it.models & bj.models) and len(it.words & bj.words) < 2:
                continue
            score = _weighted_jaccard(a_inf, b_inf, w)
            if score > best_score:
                best_score = score
                best_name = bj.name

        if best_score >= threshold and best_name:
            matches += 1
            if len(examples) < max_examples:
                examples.append((best_score, it.name, best_name))

    examples.sort(key=lambda x: x[0], reverse=True)
    return matches, examples[:max_examples]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-ekf", type=int, default=20000)
    ap.add_argument("--limit-tdm", type=int, default=19025)
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--examples", type=int, default=30)
    args = ap.parse_args()

    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    try:
        ekf = _fetch_items(session, "EKF", args.limit_ekf)
        tdm = _fetch_items(session, "TDM Electric", args.limit_tdm)

        print("## TDM ↔ EKF name-only matching report\n")
        print(f"- **EKF items**: {len(ekf)}")
        print(f"- **TDM items**: {len(tdm)}")
        print(f"- **threshold**: {args.threshold}\n")

        # Quick stats: how many have model tokens
        ekf_models = sum(1 for x in ekf if x.models)
        tdm_models = sum(1 for x in tdm if x.models)
        print("## Token stats\n")
        print(f"- **EKF with model tokens**: {ekf_models}")
        print(f"- **TDM with model tokens**: {tdm_models}\n")

        print("## Matches (EKF → TDM)\n")
        m1, ex1 = _match_report(ekf, tdm, threshold=args.threshold, max_examples=args.examples)
        print(f"- **count**: {m1}")
        if ex1:
            print(f"- **examples ({len(ex1)})**:")
            for s, a, b in ex1:
                print(f"  - **{s:.2f}** | {a[:180]}  ↔  {b[:180]}")
        print()

        print("## Matches (TDM → EKF)\n")
        m2, ex2 = _match_report(tdm, ekf, threshold=args.threshold, max_examples=args.examples)
        print(f"- **count**: {m2}")
        if ex2:
            print(f"- **examples ({len(ex2)})**:")
            for s, a, b in ex2:
                print(f"  - **{s:.2f}** | {a[:180]}  ↔  {b[:180]}")

    finally:
        session.close()


if __name__ == "__main__":
    main()


