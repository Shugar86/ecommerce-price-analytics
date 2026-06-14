"""
RU matching benchmark from live normalized offers.

The benchmark is intentionally silver/gold hybrid for a thesis demo: labels come
from stable product identifiers (barcode or brand+vendor_code), while the model
score is computed from normalized product names only. This makes the evaluation
honest: exact keys create labels, but they are not used as the similarity score.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import re
from difflib import SequenceMatcher
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import NormalizedOffer
from app.matching.text import name_only_score
from app.ml.matching import norm_brand, norm_vendor_code, normalize_barcode
from app.ml.name_normalization import normalize_title_for_matching

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BenchmarkOffer:
    """Small immutable offer projection used by the benchmark builder."""

    id: int
    source_name: str
    name: str
    brand: str
    vendor_code: str
    barcode: str
    category: str
    price_rub: float | None


@dataclass(frozen=True)
class BenchmarkPair:
    """One labelled pair in the RU product matching benchmark."""

    left_id: int
    right_id: int
    left_source: str
    right_source: str
    left_name: str
    right_name: str
    left_brand: str
    right_brand: str
    left_vendor_code: str
    right_vendor_code: str
    left_barcode: str
    right_barcode: str
    label: int
    label_source: str
    name_score: float
    price_gap_pct: float | None


@dataclass(frozen=True)
class BenchmarkMetrics:
    """Summary metrics for a threshold-based name matching baseline."""

    threshold: float
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    tn: int
    fn: int
    positives: int
    negatives: int
    total: int


def _score_names(left: str, right: str) -> float:
    """Return hybrid name-only score after deterministic title normalization.

    The score deliberately ignores ``vendor_code`` and ``barcode`` fields. If model
    numbers are present inside the title text, they are fair game: they are part of
    the names visible to the matcher and to a human reviewer.
    """
    a = normalize_title_for_matching(left)
    b = normalize_title_for_matching(right)
    score = max(name_only_score(a, b), _token_f1(a, b), _sequence_ratio(a, b))
    ma, mb = _modelish_tokens(a), _modelish_tokens(b)
    if ma and mb and not (ma & mb):
        score = min(score, 0.62)
    elif bool(ma) != bool(mb):
        score = min(score, 0.78)
    na, nb = _numberish_tokens(a), _numberish_tokens(b)
    if na and nb and na != nb:
        score = min(score, 0.74)
    return round(score, 6)


def _title_tokens(title: str) -> set[str]:
    """Normalized title tokens useful for benchmark filtering."""
    return {x for x in normalize_title_for_matching(title).split() if len(x) >= 2}


_MODELISH_RE = re.compile(r"(?=.*\d)[a-zа-я0-9][a-zа-я0-9._/\-]{2,}", re.IGNORECASE)


def _modelish_tokens(title: str) -> set[str]:
    """Model/article-like tokens present inside a normalized title."""
    return {
        token.replace("_", "-").replace("/", "-")
        for token in title.split()
        if _MODELISH_RE.fullmatch(token) and ("-" in token or len(token) >= 5)
    }


def _numberish_tokens(title: str) -> set[str]:
    """Tokens with digits: dimensions, amperage, package sizes, model fragments."""
    return {token for token in title.split() if any(ch.isdigit() for ch in token)}


def _too_generic_title(title: str) -> bool:
    """Filter out supplier placeholders like 'Деталь' that make bad negatives."""
    tokens = _title_tokens(title)
    if len(tokens) < 3:
        return True
    generic = {"деталь", "товар", "изделие", "запчасть", "комплект", "qty"}
    return tokens <= generic


def _token_f1(left: str, right: str) -> float:
    """Token overlap F1 for normalized titles."""
    a = {x for x in left.split() if len(x) >= 2}
    b = {x for x in right.split() if len(x) >= 2}
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    precision = inter / len(a)
    recall = inter / len(b)
    return 2 * precision * recall / (precision + recall)


def _sequence_ratio(left: str, right: str) -> float:
    """String similarity for nearly identical supplier titles."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _price_gap_pct(left: float | None, right: float | None) -> float | None:
    """Return relative price gap in percent if both prices are valid."""
    if left is None or right is None or left <= 0:
        return None
    return round((right - left) / left * 100.0, 6)


def _pair_key(left: BenchmarkOffer, right: BenchmarkOffer) -> tuple[int, int]:
    """Stable unordered pair id."""
    return (left.id, right.id) if left.id < right.id else (right.id, left.id)


def _make_pair(
    left: BenchmarkOffer,
    right: BenchmarkOffer,
    *,
    label: int,
    label_source: str,
) -> BenchmarkPair:
    """Create a serializable pair row."""
    a, b = (left, right) if left.id < right.id else (right, left)
    return BenchmarkPair(
        left_id=a.id,
        right_id=b.id,
        left_source=a.source_name,
        right_source=b.source_name,
        left_name=a.name,
        right_name=b.name,
        left_brand=a.brand,
        right_brand=b.brand,
        left_vendor_code=a.vendor_code,
        right_vendor_code=b.vendor_code,
        left_barcode=a.barcode,
        right_barcode=b.barcode,
        label=label,
        label_source=label_source,
        name_score=_score_names(a.name, b.name),
        price_gap_pct=_price_gap_pct(a.price_rub, b.price_rub),
    )


def offer_from_orm(row: NormalizedOffer) -> BenchmarkOffer:
    """Convert ORM offer to compact benchmark projection."""
    return BenchmarkOffer(
        id=int(row.id),
        source_name=str(row.source_name or ""),
        name=str(row.name or "").strip(),
        brand=norm_brand(row.brand),
        vendor_code=norm_vendor_code(row.vendor_code),
        barcode=normalize_barcode(row.barcode) or "",
        category=str(row.category or "").strip(),
        price_rub=float(row.price_rub) if row.price_rub is not None else None,
    )


def load_offers_for_benchmark(
    session: Session,
    *,
    sources: Sequence[str] | None = None,
    per_source_limit: int = 3000,
) -> list[BenchmarkOffer]:
    """Load offers from DB for benchmark construction.

    Args:
        session: SQLAlchemy session.
        sources: Optional source names. If empty, all sources are used.
        per_source_limit: Maximum number of offers per source.

    Returns:
        Offer projections with non-empty names and either barcode or vendor_code.
    """
    source_names = list(sources or [])
    if not source_names:
        source_names = list(
            session.scalars(
                select(NormalizedOffer.source_name)
                .distinct()
                .order_by(NormalizedOffer.source_name)
            ).all()
        )
    out: list[BenchmarkOffer] = []
    for source in source_names:
        rows = session.scalars(
            select(NormalizedOffer)
            .where(NormalizedOffer.source_name == source)
            .where(NormalizedOffer.name.is_not(None))
            .order_by(NormalizedOffer.id)
            .limit(per_source_limit)
        ).all()
        for row in rows:
            item = offer_from_orm(row)
            if item.name and (item.barcode or item.vendor_code):
                out.append(item)
    return out


def _positive_pairs(
    offers: Sequence[BenchmarkOffer],
    *,
    max_pairs: int,
    per_key_limit: int,
) -> list[BenchmarkPair]:
    """Build positive pairs from stable identifiers across different sources."""
    pairs: list[BenchmarkPair] = []
    seen: set[tuple[int, int]] = set()
    seen_signature: set[tuple[str, str, str, str]] = set()

    by_barcode: dict[str, list[BenchmarkOffer]] = defaultdict(list)
    by_vendor_brand: dict[tuple[str, str], list[BenchmarkOffer]] = defaultdict(list)
    for offer in offers:
        if offer.barcode:
            by_barcode[offer.barcode].append(offer)
        if offer.brand and offer.vendor_code:
            by_vendor_brand[(offer.brand, offer.vendor_code)].append(offer)

    for group in by_barcode.values():
        if len(pairs) >= max_pairs:
            break
        for left, right in combinations(group[:per_key_limit], 2):
            if left.source_name == right.source_name:
                continue
            if _too_generic_title(left.name) or _too_generic_title(right.name):
                continue
            if normalize_title_for_matching(left.name) == normalize_title_for_matching(right.name):
                continue
            key = _pair_key(left, right)
            if key in seen:
                continue
            sig = (
                "barcode",
                left.barcode,
                "|".join(sorted((left.source_name, right.source_name))),
                "|".join(sorted((normalize_title_for_matching(left.name), normalize_title_for_matching(right.name)))),
            )
            if sig in seen_signature:
                continue
            seen_signature.add(sig)
            seen.add(key)
            pairs.append(_make_pair(left, right, label=1, label_source="exact_barcode"))
            if len(pairs) >= max_pairs:
                break

    for group in by_vendor_brand.values():
        if len(pairs) >= max_pairs:
            break
        if len({x.source_name for x in group}) < 2:
            continue
        for left, right in combinations(group[:per_key_limit], 2):
            if left.source_name == right.source_name:
                continue
            if _too_generic_title(left.name) or _too_generic_title(right.name):
                continue
            if normalize_title_for_matching(left.name) == normalize_title_for_matching(right.name):
                continue
            key = _pair_key(left, right)
            if key in seen:
                continue
            sig = (
                "vendor_brand",
                f"{left.brand}:{left.vendor_code}",
                "|".join(sorted((left.source_name, right.source_name))),
                "|".join(sorted((normalize_title_for_matching(left.name), normalize_title_for_matching(right.name)))),
            )
            if sig in seen_signature:
                continue
            seen_signature.add(sig)
            seen.add(key)
            pairs.append(
                _make_pair(left, right, label=1, label_source="exact_vendor_brand")
            )
            if len(pairs) >= max_pairs:
                break

    return pairs


def _negative_pairs(
    offers: Sequence[BenchmarkOffer],
    positive_keys: set[tuple[int, int]],
    *,
    max_pairs: int,
    comparisons_per_brand: int,
) -> list[BenchmarkPair]:
    """Build hard negatives: same brand, different code, different source."""
    by_brand: dict[str, list[BenchmarkOffer]] = defaultdict(list)
    for offer in offers:
        if offer.brand and offer.vendor_code:
            by_brand[offer.brand].append(offer)

    candidates: list[BenchmarkPair] = []
    per_brand_cap = max(25, max_pairs // 25)
    for brand, group in by_brand.items():
        if len(group) < 2:
            continue
        checked = 0
        brand_candidates: list[BenchmarkPair] = []
        seen_signature: set[tuple[str, str, str, str]] = set()
        for left, right in combinations(group, 2):
            if checked >= comparisons_per_brand:
                break
            checked += 1
            if left.source_name == right.source_name:
                continue
            if left.vendor_code == right.vendor_code:
                continue
            key = _pair_key(left, right)
            if key in positive_keys:
                continue
            if _too_generic_title(left.name) or _too_generic_title(right.name):
                continue
            left_norm = normalize_title_for_matching(left.name)
            right_norm = normalize_title_for_matching(right.name)
            if left_norm == right_norm:
                continue
            sig = (
                brand,
                "|".join(sorted((left.vendor_code, right.vendor_code))),
                "|".join(sorted((left.source_name, right.source_name))),
                "|".join(sorted((left_norm, right_norm))),
            )
            if sig in seen_signature:
                continue
            seen_signature.add(sig)
            pair = _make_pair(
                left,
                right,
                label=0,
                label_source=f"hard_negative_same_brand:{brand}",
            )
            if pair.name_score <= 0:
                continue
            brand_candidates.append(pair)
        brand_candidates.sort(key=lambda p: p.name_score, reverse=True)
        candidates.extend(brand_candidates[:per_brand_cap])
    candidates.sort(key=lambda p: p.name_score, reverse=True)
    return candidates[:max_pairs]


def build_ru_matching_pairs(
    offers: Sequence[BenchmarkOffer],
    *,
    max_positive_pairs: int = 2500,
    max_negative_pairs: int = 2500,
    per_key_limit: int = 12,
    comparisons_per_brand: int = 20000,
) -> list[BenchmarkPair]:
    """Build labelled benchmark pairs from loaded offers."""
    positives = _positive_pairs(
        offers,
        max_pairs=max_positive_pairs,
        per_key_limit=per_key_limit,
    )
    positive_keys = {(p.left_id, p.right_id) for p in positives}
    negatives = _negative_pairs(
        offers,
        positive_keys,
        max_pairs=max_negative_pairs,
        comparisons_per_brand=comparisons_per_brand,
    )
    rows = positives + negatives
    rows.sort(key=lambda p: (p.label, p.name_score), reverse=True)
    return rows


def metrics_at_threshold(
    pairs: Sequence[BenchmarkPair],
    threshold: float,
) -> BenchmarkMetrics:
    """Compute binary metrics for ``name_score >= threshold``."""
    tp = fp = tn = fn = 0
    for pair in pairs:
        pred = pair.name_score >= threshold
        actual = pair.label == 1
        if pred and actual:
            tp += 1
        elif pred and not actual:
            fp += 1
        elif not pred and not actual:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    positives = sum(1 for p in pairs if p.label == 1)
    negatives = len(pairs) - positives
    return BenchmarkMetrics(
        threshold=round(float(threshold), 4),
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        positives=positives,
        negatives=negatives,
        total=len(pairs),
    )


def threshold_sweep(
    pairs: Sequence[BenchmarkPair],
    *,
    step: float = 0.02,
) -> list[BenchmarkMetrics]:
    """Compute metrics for thresholds from 0 to 1 inclusive."""
    if step <= 0:
        raise ValueError("step must be positive")
    n = int(math.floor(1.0 / step))
    thresholds = [round(i * step, 6) for i in range(n + 1)]
    if thresholds[-1] < 1.0:
        thresholds.append(1.0)
    return [metrics_at_threshold(pairs, t) for t in thresholds]


def best_f1(metrics: Sequence[BenchmarkMetrics]) -> BenchmarkMetrics:
    """Return metric row with best F1, then higher precision."""
    if not metrics:
        return BenchmarkMetrics(0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
    return max(metrics, key=lambda m: (m.f1, m.precision, m.recall))


def write_pairs_csv(path: Path, pairs: Sequence[BenchmarkPair]) -> None:
    """Write benchmark pairs to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(pairs[0]).keys()) if pairs else list(BenchmarkPair.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(asdict(pair))


def write_metrics_csv(path: Path, metrics: Sequence[BenchmarkMetrics]) -> None:
    """Write threshold sweep metrics to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(metrics[0]).keys()) if metrics else list(BenchmarkMetrics.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in metrics:
            writer.writerow(asdict(row))


def write_summary_json(
    path: Path,
    *,
    pairs: Sequence[BenchmarkPair],
    metrics: Sequence[BenchmarkMetrics],
    sources: Sequence[str],
) -> dict[str, object]:
    """Write JSON summary and return it."""
    best = best_f1(metrics)
    label_sources: dict[str, int] = defaultdict(int)
    for pair in pairs:
        label_sources[pair.label_source] += 1
    summary: dict[str, object] = {
        "sources": list(sources),
        "pairs_total": len(pairs),
        "positive_pairs": sum(1 for p in pairs if p.label == 1),
        "negative_pairs": sum(1 for p in pairs if p.label == 0),
        "label_sources": dict(sorted(label_sources.items())),
        "best_f1": asdict(best),
        "note": (
            "Labels come from barcode or brand+vendor_code. Scores use only "
            "normalized names, so this evaluates title similarity on live RU feeds."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def render_benchmark_plots(
    out_dir: Path,
    pairs: Sequence[BenchmarkPair],
    metrics: Sequence[BenchmarkMetrics],
) -> list[str]:
    """Render thesis-ready PNG plots for the benchmark."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    best = best_f1(metrics)

    # Professional light academic style for print/VKR
    plt.rcParams.update(
        {
            "figure.figsize": (11, 6.2),
            "font.family": ["DejaVu Sans", "sans-serif"],
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.color": "#cbd5e1",
            "axes.edgecolor": "#64748b",
            "axes.facecolor": "#ffffff",
            "figure.facecolor": "#ffffff",
            "savefig.facecolor": "#ffffff",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.15,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": True,
            "legend.framealpha": 0.95,
        }
    )
    created: list[str] = []

    # 1. Score distribution (high contrast for print)
    pos_scores = [p.name_score for p in pairs if p.label == 1]
    neg_scores = [p.name_score for p in pairs if p.label == 0]
    fig1, ax1 = plt.subplots(figsize=(11, 6))
    ax1.hist(
        pos_scores,
        bins=40,
        alpha=0.85,
        label="Совпадения (позитивы)",
        color="#166534",
        edgecolor="#052e16",
        linewidth=0.4,
    )
    ax1.hist(
        neg_scores,
        bins=40,
        alpha=0.75,
        label="Hard negatives (негативы)",
        color="#9a3412",
        edgecolor="#431407",
        linewidth=0.4,
    )
    ax1.axvspan(0.15, 0.45, color="#94a3b8", alpha=0.12, label="перекрытие 0,15–0,45")
    ax1.axvspan(0.25, 0.50, color="#64748b", alpha=0.22, label="операционная зона 0,25–0,50")
    ax1.set_xlabel("Оценка сходства наименований (name_score)")
    ax1.set_ylabel("Число пар")
    ax1.set_title("RuEcom-2026 — распределение оценок сходства (совпадения vs hard negatives)", pad=12)
    ax1.legend(loc="upper right", fontsize=11)
    ax1.set_xlim(0, 1)
    p1 = out_dir / "ru_match_score_distribution.png"
    fig1.savefig(p1, dpi=300)
    plt.close(fig1)
    created.append(str(p1))

    # 2. PR curve
    fig2, ax2 = plt.subplots(figsize=(10, 6.5))
    recalls = [m.recall for m in metrics]
    precisions = [m.precision for m in metrics]
    ax2.plot(
        recalls,
        precisions,
        marker="o",
        markersize=4.5,
        linewidth=2.2,
        color="#1e40af",
        label="Precision-Recall",
    )
    ax2.fill_between(recalls, precisions, alpha=0.12, color="#1e40af")
    ax2.set_xlabel("Recall")
    ax2.set_ylabel("Precision")
    ax2.set_title("RU Benchmark — Precision-Recall Curve (by similarity threshold)", pad=12)
    ax2.set_xlim(0, 1.02)
    ax2.set_ylim(0, 1.02)
    ax2.legend(loc="lower left")
    p2 = out_dir / "ru_precision_recall.png"
    fig2.savefig(p2, dpi=300)
    plt.close(fig2)
    created.append(str(p2))

    # 3. F1 vs threshold
    fig3, ax3 = plt.subplots(figsize=(10, 5.8))
    thresholds = [m.threshold for m in metrics]
    f1s = [m.f1 for m in metrics]
    ax3.plot(thresholds, f1s, color="#4338ca", linewidth=2.5, label="F1 score")
    ax3.axvline(
        best.threshold,
        color="#b91c1c",
        linestyle="--",
        linewidth=1.8,
        label=f"Best threshold = {best.threshold:.2f} (F1={best.f1:.3f})",
    )
    ax3.scatter([best.threshold], [best.f1], s=90, color="#b91c1c", zorder=5, edgecolors="white", linewidths=1.5)
    ax3.set_xlabel("Similarity threshold")
    ax3.set_ylabel("F1 score")
    ax3.set_title("RU Benchmark — F1 Score vs Decision Threshold", pad=12)
    ax3.legend(loc="best")
    ax3.set_ylim(0, 1.05)
    p3 = out_dir / "ru_f1_by_threshold.png"
    fig3.savefig(p3, dpi=300)
    plt.close(fig3)
    created.append(str(p3))

    # 4. Confusion matrix (print-friendly Blues, large numbers)
    fig4, ax4 = plt.subplots(figsize=(7.5, 6.5))
    matrix = [[best.tn, best.fp], [best.fn, best.tp]]
    im = ax4.imshow(matrix, cmap="Blues", aspect="equal")
    ax4.set_xticks([0, 1])
    ax4.set_xticklabels(["Predicted 0 (non-match)", "Predicted 1 (match)"], fontsize=11)
    ax4.set_yticks([0, 1])
    ax4.set_yticklabels(["True 0 (non-match)", "True 1 (match)"], fontsize=11)
    for i in range(2):
        for j in range(2):
            val = matrix[i][j]
            text_color = "white" if val > max(matrix[0][0], matrix[1][1]) * 0.6 else "#1e2937"
            ax4.text(j, i, f"{val:,}", ha="center", va="center", fontsize=18, fontweight="bold", color=text_color)
    ax4.set_title(f"Confusion Matrix @ threshold = {best.threshold:.2f}", pad=10, fontsize=13)
    cbar = fig4.colorbar(im, ax=ax4, fraction=0.046, pad=0.04, shrink=0.82)
    cbar.ax.tick_params(labelsize=9)
    p4 = out_dir / "ru_confusion_matrix.png"
    fig4.savefig(p4, dpi=300)
    plt.close(fig4)
    created.append(str(p4))

    return created


def write_top_examples(
    path: Path,
    pairs: Sequence[BenchmarkPair],
    *,
    limit: int = 30,
) -> None:
    """Write a compact CSV with visually useful match and error examples."""
    path.parent.mkdir(parents=True, exist_ok=True)
    top_matches = sorted(
        (p for p in pairs if p.label == 1),
        key=lambda p: p.name_score,
        reverse=True,
    )[:limit]
    hard_negatives = sorted(
        (p for p in pairs if p.label == 0),
        key=lambda p: p.name_score,
        reverse=True,
    )[:limit]
    fieldnames = [
        "bucket",
        "name_score",
        "label",
        "label_source",
        "left_source",
        "right_source",
        "left_name",
        "right_name",
        "left_vendor_code",
        "right_vendor_code",
        "price_gap_pct",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for bucket, rows in (("true_match", top_matches), ("hard_negative", hard_negatives)):
            for row in rows:
                writer.writerow(
                    {
                        "bucket": bucket,
                        "name_score": row.name_score,
                        "label": row.label,
                        "label_source": row.label_source,
                        "left_source": row.left_source,
                        "right_source": row.right_source,
                        "left_name": row.left_name,
                        "right_name": row.right_name,
                        "left_vendor_code": row.left_vendor_code,
                        "right_vendor_code": row.right_vendor_code,
                        "price_gap_pct": row.price_gap_pct,
                    }
                )


def read_pairs_csv(path: Path) -> list[BenchmarkPair]:
    """Read pairs CSV back into dataclasses for tests or re-rendering."""
    out: list[BenchmarkPair] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            gap_raw = row.get("price_gap_pct") or ""
            out.append(
                BenchmarkPair(
                    left_id=int(row["left_id"]),
                    right_id=int(row["right_id"]),
                    left_source=row["left_source"],
                    right_source=row["right_source"],
                    left_name=row["left_name"],
                    right_name=row["right_name"],
                    left_brand=row["left_brand"],
                    right_brand=row["right_brand"],
                    left_vendor_code=row["left_vendor_code"],
                    right_vendor_code=row["right_vendor_code"],
                    left_barcode=row["left_barcode"],
                    right_barcode=row["right_barcode"],
                    label=int(row["label"]),
                    label_source=row["label_source"],
                    name_score=float(row["name_score"]),
                    price_gap_pct=float(gap_raw) if gap_raw else None,
                )
            )
    return out


def source_names_from_env(raw: str | None) -> list[str]:
    """Parse comma-separated source list from env/CLI."""
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]
