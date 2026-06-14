#!/usr/bin/env python3
"""Расширенные метрики качества сопоставления на эталонном наборе RuEcom-2026.

Вычисляет:
- ROC-AUC и PR-AUC
- Bootstrap 95% CI для Precision, Recall, F1 (1000 итераций)
- Сохраняет результаты в artifacts/ru_benchmark/extended_metrics.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_recall_curve,
    roc_curve,
)

ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = ROOT / "artifacts" / "ru_benchmark"


def load_benchmark() -> tuple[np.ndarray, np.ndarray]:
    """Загрузить эталонный набор из pairs.csv."""
    pairs_csv = BENCHMARK_DIR / "pairs.csv"
    if not pairs_csv.exists():
        raise FileNotFoundError(f"Файл не найден: {pairs_csv}")

    import csv
    scores, labels = [], []
    with open(pairs_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # pairs.csv: name_score — оценка текстового сходства, label — 0/1
            scores.append(float(row.get("name_score", 0)))
            labels.append(int(row.get("label", 0)))
    return np.array(scores), np.array(labels)


def bootstrap_ci(
    scores: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    n_iter: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    """Bootstrap-доверительные интервалы для Precision, Recall, F1."""
    rng = random.Random(seed)
    n = len(scores)
    p_list, r_list, f_list = [], [], []

    for _ in range(n_iter):
        idx = [rng.randint(0, n - 1) for _ in range(n)]
        s = scores[idx]
        y = labels[idx]
        pred = (s >= threshold).astype(int)

        tp = int(np.sum((pred == 1) & (y == 1)))
        fp = int(np.sum((pred == 1) & (y == 0)))
        fn = int(np.sum((pred == 0) & (y == 1)))

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        p_list.append(prec)
        r_list.append(rec)
        f_list.append(f1)

    alpha = (1 - ci) / 2

    def ci_for(vals: list[float]) -> dict[str, float]:
        arr = sorted(vals)
        lo = arr[int(alpha * n_iter)]
        hi = arr[int((1 - alpha) * n_iter)]
        return {"mean": float(np.mean(vals)), "lo": lo, "hi": hi}

    return {
        "precision_ci": ci_for(p_list),
        "recall_ci": ci_for(r_list),
        "f1_ci": ci_for(f_list),
    }


def main() -> None:
    scores, labels = load_benchmark()
    print(f"Loaded {len(scores)} pairs: {int(labels.sum())} positive, {int((1-labels).sum())} negative")

    # Текущий threshold = 0.28 (из существующего анализа)
    threshold = 0.28
    pred = (scores >= threshold).astype(int)

    # Базовые метрики при threshold
    tp = int(np.sum((pred == 1) & (labels == 1)))
    fp = int(np.sum((pred == 1) & (labels == 0)))
    tn = int(np.sum((pred == 0) & (labels == 0)))
    fn = int(np.sum((pred == 0) & (labels == 1)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # ROC-AUC
    roc_auc = float(roc_auc_score(labels, scores))

    # PR-AUC (Average Precision)
    pr_auc = float(average_precision_score(labels, scores))

    # Bootstrap CI
    print("Computing bootstrap CI (1000 iterations)...")
    ci_results = bootstrap_ci(scores, labels, threshold, n_iter=1000)

    result: dict[str, Any] = {
        "threshold": threshold,
        "n_total": int(len(scores)),
        "n_positive": int(labels.sum()),
        "n_negative": int((1 - labels).sum()),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "bootstrap_95ci": {
            "precision": {k: round(v, 4) for k, v in ci_results["precision_ci"].items()},
            "recall": {k: round(v, 4) for k, v in ci_results["recall_ci"].items()},
            "f1": {k: round(v, 4) for k, v in ci_results["f1_ci"].items()},
        },
    }

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BENCHMARK_DIR / "extended_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Расширенные метрики (порог {threshold}) ===")
    print(f"Precision:  {precision:.4f}  [CI 95%: {ci_results['precision_ci']['lo']:.4f} – {ci_results['precision_ci']['hi']:.4f}]")
    print(f"Recall:     {recall:.4f}  [CI 95%: {ci_results['recall_ci']['lo']:.4f} – {ci_results['recall_ci']['hi']:.4f}]")
    print(f"F1-score:   {f1:.4f}  [CI 95%: {ci_results['f1_ci']['lo']:.4f} – {ci_results['f1_ci']['hi']:.4f}]")
    print(f"ROC-AUC:    {roc_auc:.4f}")
    print(f"PR-AUC:     {pr_auc:.4f}")
    print(f"\nСохранено в: {out_path}")


if __name__ == "__main__":
    main()
