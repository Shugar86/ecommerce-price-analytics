#!/usr/bin/env python3
"""Оценка точности в «серой зоне» сходства до и после LLM (Gemini).

Читает ``artifacts/ru_benchmark/pairs.csv``, отбирает пары с
``gray_lo <= name_score <= gray_hi`` (по умолчанию 0.25–0.5).

Базовый классификатор: «совпадение», если ``name_score >= threshold`` (по умолчанию
0.28, как в §2.2.6).

С LLM: для пар, где базовый классификатор предсказал «совпадение», вызывается
``GeminiValidator.validate_pair``; итоговое предсказание положительное только если
``match is True`` и ``confidence >= min_conf`` (по умолчанию 0.8).

При отсутствии ``GOOGLE_API_KEY`` API не вызывается: сохраняются только метрики
базового уровня и строится график с одним столбцом (в тексте ВКР указывается
необходимость ключа для полного прогона).

Запуск из корня репозитория::

    .venv/bin/python tools/eval_gemini_gray_zone.py
    .venv/bin/python tools/eval_gemini_gray_zone.py --max-api-calls 80
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.gemini_validator import gemini_validator_from_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAIRS = ROOT / "artifacts" / "ru_benchmark" / "pairs.csv"
OUT_JSON = ROOT / "artifacts" / "ru_benchmark" / "gemini_gray_zone.json"
OUT_PNG = ROOT / "artifacts" / "ru_benchmark" / "gemini_gray_zone_impact.png"


def _precision(tp: int, fp: int) -> float:
    den = tp + fp
    return (tp / den) if den > 0 else 0.0


def _recall(tp: int, fn: int) -> float:
    den = tp + fn
    return (tp / den) if den > 0 else 0.0


def load_gray_zone_rows(
    path: Path,
    *,
    gray_lo: float,
    gray_hi: float,
    threshold: float,
) -> list[dict[str, object]]:
    """Загрузить строки CSV в «серой зоне»."""
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            try:
                score = float(raw.get("name_score") or 0)
            except ValueError:
                continue
            if not (gray_lo <= score <= gray_hi):
                continue
            label = int(raw.get("label") or 0)
            base_pos = score >= threshold
            rows.append(
                {
                    "left_name": str(raw.get("left_name") or ""),
                    "right_name": str(raw.get("right_name") or ""),
                    "name_score": score,
                    "label": label,
                    "baseline_positive": base_pos,
                }
            )
    return rows


def eval_with_llm(
    rows: list[dict[str, object]],
    *,
    threshold: float,
    min_conf: float,
    max_calls: int,
) -> tuple[list[dict[str, object]], int]:
    """Вернуть обновлённые строки с полем ``llm_positive`` и число вызовов API."""
    validator = gemini_validator_from_env()
    if validator is None or not validator.is_configured:
        return rows, 0

    calls = 0
    out: list[dict[str, object]] = []
    for r in rows:
        item = dict(r)
        if not item.get("baseline_positive"):
            item["llm_positive"] = False
            item["llm_skipped"] = True
            out.append(item)
            continue
        if calls >= max_calls:
            item["llm_positive"] = bool(item.get("baseline_positive"))
            item["llm_skipped"] = True
            item["llm_error"] = "max_api_calls"
            out.append(item)
            continue

        left = str(item["left_name"])
        right = str(item["right_name"])
        verdict = validator.validate_pair(left, right)
        calls += 1
        err = verdict.get("error")
        if err:
            item["llm_error"] = str(err)
            item["llm_positive"] = bool(item.get("baseline_positive"))
            item["llm_skipped"] = False
            out.append(item)
            continue

        match_ok = bool(verdict.get("match"))
        conf = float(verdict.get("confidence") or 0.0)
        item["llm_positive"] = match_ok and conf >= min_conf
        item["llm_match"] = match_ok
        item["llm_confidence"] = conf
        item["llm_skipped"] = False
        out.append(item)
    return out, calls


def confusion_subset(rows: list[dict[str, object]], pred_key: str) -> tuple[int, int, int, int]:
    """TP, FP, TN, FN для выбранного ключа предсказания (bool)."""
    tp = fp = tn = fn = 0
    for r in rows:
        y = int(r["label"])
        pred = bool(r[pred_key])
        if y == 1 and pred:
            tp += 1
        elif y == 0 and pred:
            fp += 1
        elif y == 0 and not pred:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def render_bar_chart(
    path: Path,
    baseline_p: float,
    after_p: float | None,
    *,
    api_used: bool,
) -> None:
    """Столбчатая диаграмма Precision в «серой зоне»."""
    import matplotlib.pyplot as plt

    if after_p is None:
        labels = ["Базовый порог\n(name_score ≥ 0,28)"]
        values = [baseline_p]
        colors = ["#64748b"]
    else:
        labels = [
            "Базовый порог\n(name_score ≥ 0,28)",
            "+ фильтр Gemini 2.5 Flash\n(match ∧ conf ≥ 0,8)",
        ]
        values = [baseline_p, after_p]
        colors = ["#94a3b8", "#2563eb"]

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Precision (серый зона)")
    title = "Точность на подмножестве серой зоны сходства"
    if not api_used and after_p is None:
        title += "\n(LLM-прогон не выполнялся: нет GOOGLE_API_KEY)"
    ax.set_title(title, fontsize=11)
    for b, v in zip(bars, values, strict=True):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.1%}", ha="center", fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-png", type=Path, default=OUT_PNG)
    parser.add_argument("--gray-lo", type=float, default=0.25)
    parser.add_argument("--gray-hi", type=float, default=0.5)
    parser.add_argument("--threshold", type=float, default=0.28)
    parser.add_argument("--min-conf", type=float, default=0.8)
    parser.add_argument("--max-api-calls", type=int, default=200)
    args = parser.parse_args()

    if not args.pairs.is_file():
        raise SystemExit(f"Нет файла пар: {args.pairs}")

    rows = load_gray_zone_rows(
        args.pairs,
        gray_lo=args.gray_lo,
        gray_hi=args.gray_hi,
        threshold=args.threshold,
    )
    n_gray = len(rows)
    n_baseline_pos = sum(1 for r in rows if r["baseline_positive"])

    tp_b, fp_b, tn_b, fn_b = confusion_subset(rows, "baseline_positive")
    p_baseline = _precision(tp_b, fp_b)
    r_baseline = _recall(tp_b, fn_b)

    rows_llm, api_calls = eval_with_llm(
        rows,
        threshold=args.threshold,
        min_conf=args.min_conf,
        max_calls=args.max_api_calls,
    )

    p_after: float | None = None
    r_after: float | None = None
    api_used = api_calls > 0

    if api_used:
        tp2, fp2, tn2, fn2 = confusion_subset(rows_llm, "llm_positive")
        p_after = _precision(tp2, fp2)
        r_after = _recall(tp2, fn2)

    payload: dict[str, object] = {
        "gray_score_range": [args.gray_lo, args.gray_hi],
        "fuzzy_threshold": args.threshold,
        "min_llm_confidence": args.min_conf,
        "n_pairs_in_gray_zone": n_gray,
        "n_baseline_predicted_positive": n_baseline_pos,
        "baseline": {
            "tp": tp_b,
            "fp": fp_b,
            "tn": tn_b,
            "fn": fn_b,
            "precision": round(p_baseline, 4),
            "recall": round(r_baseline, 4),
        },
        "api_calls": api_calls,
        "llm_applied": api_used,
    }
    if p_after is not None:
        payload["with_llm_filter"] = {
            "precision": round(p_after, 4),
            "recall": round(r_after, 4),
            "delta_precision_pp": round((p_after - p_baseline) * 100, 2),
        }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with args.out_json.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Сохранено: %s", args.out_json)

    render_bar_chart(
        args.out_png,
        p_baseline,
        p_after,
        api_used=api_used,
    )
    logger.info("График: %s", args.out_png)


if __name__ == "__main__":
    main()
