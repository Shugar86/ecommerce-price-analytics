#!/usr/bin/env python3
"""Построение иллюстраций главы 3 из реальных артефактов эксперимента RuEcom-2026.

Все графики строятся ТОЛЬКО из сохранённых результатов контрольного прогона
(``artifacts/ru_benchmark`` и ``artifacts/ru_benchmark_electric``); синтетические
или «условные» числа не используются.

Запуск из корня репозитория::

    python tools/build_chapter3_visuals.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

FIGURE_DPI = 300

# Палитра главы 3 — согласована с академическим стилем главы 2.
COLOR_PRIMARY = "#1e40af"
COLOR_ACCENT = "#166534"
COLOR_WARN = "#b91c1c"
COLOR_NEUTRAL = "#64748b"
COLOR_GRID = "#e2e8f0"
COLOR_OVERLAP = "#94a3b8"
COLOR_TP = "#dcfce7"
COLOR_TN = "#dbeafe"
COLOR_FP = "#fee2e2"
COLOR_FN = "#fef3c7"


@dataclass(frozen=True)
class ThresholdRow:
    """Одна точка развёртки метрик по порогу из ``metrics.csv``."""

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


def _comma(value: float, digits: int = 2) -> str:
    """Форматирует число с запятой в качестве десятичного разделителя."""
    return f"{value:.{digits}f}".replace(".", ",")


def _pct(part: int, whole: int) -> str:
    """Доля part/whole в процентах для подписи в ячейке матрицы."""
    if whole <= 0:
        return "—"
    return _comma(100.0 * part / whole, 1) + "%"


def _read_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл с осмысленным логированием ошибок."""
    if not path.is_file():
        raise FileNotFoundError(f"Не найден артефакт: {path}")
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Некорректный JSON в {path}: {exc}") from exc


def _read_metrics_csv(path: Path) -> list[ThresholdRow]:
    """Читает развёртку метрик по порогу из ``metrics.csv``."""
    if not path.is_file():
        raise FileNotFoundError(f"Не найден файл развёртки метрик: {path}")
    rows: list[ThresholdRow] = []
    with path.open(encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            try:
                rows.append(
                    ThresholdRow(
                        threshold=float(rec["threshold"]),
                        precision=float(rec["precision"]),
                        recall=float(rec["recall"]),
                        f1=float(rec["f1"]),
                        tp=int(rec["tp"]),
                        fp=int(rec["fp"]),
                        tn=int(rec["tn"]),
                        fn=int(rec["fn"]),
                        positives=int(rec["positives"]),
                        negatives=int(rec["negatives"]),
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Пропущена строка metrics.csv (%s): %s", exc, rec)
    rows.sort(key=lambda r: r.threshold)
    return rows


def _read_scores_by_label(path: Path) -> tuple[list[float], list[float]]:
    """Читает оценки сходства по классу метки из ``pairs.csv``."""
    matches: list[float] = []
    nonmatches: list[float] = []
    if not path.is_file():
        logger.warning("pairs.csv не найден: %s — график распределения пропущен", path)
        return matches, nonmatches
    with path.open(encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            try:
                score = float(rec["name_score"])
                label = int(rec["label"])
            except (KeyError, ValueError):
                continue
            (matches if label == 1 else nonmatches).append(score)
    return matches, nonmatches


def _operating_row(rows: list[ThresholdRow], best_threshold: float) -> ThresholdRow:
    """Возвращает строку развёртки, ближайшую к рабочему порогу."""
    return min(rows, key=lambda r: abs(r.threshold - best_threshold))


def _apply_vkr_style(plt: Any) -> None:
    """Единое оформление иллюстраций главы 3 (печать / DOCX)."""
    plt.rcParams.update(
        {
            "font.family": ["DejaVu Sans", "sans-serif"],
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "axes.grid": True,
            "grid.alpha": 0.35,
            "grid.color": COLOR_GRID,
            "grid.linewidth": 0.7,
            "axes.edgecolor": "#64748b",
            "axes.facecolor": "#ffffff",
            "figure.facecolor": "#ffffff",
            "savefig.facecolor": "#ffffff",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.18,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": True,
            "legend.framealpha": 0.96,
            "legend.edgecolor": COLOR_GRID,
        }
    )


def _new_axes(plt: Any, figsize: tuple[float, float]):
    """Создаёт фигуру и оси с сеткой под данными."""
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_axisbelow(True)
    return fig, ax


def _save_fig(fig: Any, out_path: Path, plt: Any) -> None:
    """Сохраняет PNG с единым DPI и закрывает фигуру."""
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor="white")
    plt.close(fig)
    logger.info("Создан: %s", out_path)


def render_confusion_matrix(summary: dict[str, Any], out_path: Path, plt: Any) -> None:
    """Строит матрицу ошибок с цветовой кодировкой и долями по строкам."""
    best = summary["best_f1"]
    thr = float(best["threshold"])
    tp, fp, tn, fn = int(best["tp"]), int(best["fp"]), int(best["tn"]), int(best["fn"])
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    pos_total = tp + fn
    neg_total = fp + tn

    # Строка = факт, столбец = прогноз.
    counts = [[tp, fn], [fp, tn]]
    colors = [[COLOR_TP, COLOR_FN], [COLOR_FP, COLOR_TN]]
    labels = [
        [("TP", tp, pos_total), ("FN", fn, pos_total)],
        [("FP", fp, neg_total), ("TN", tn, neg_total)],
    ]
    captions = [
        ["верное совпадение", "пропуск"],
        ["ложное совпадение", "верное различие"],
    ]

    fig, ax = plt.subplots(figsize=(9.0, 6.2))
    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(1.5, -0.5)
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Прогноз:\nсовпадение", "Прогноз:\nразличие"], fontsize=11)
    ax.set_yticklabels(["Факт:\nсовпадение", "Факт:\nразличие"], fontsize=11)

    for row in range(2):
        for col in range(2):
            code, value, row_total = labels[row][col]
            face = colors[row][col]
            ax.add_patch(
                plt.Rectangle(
                    (col - 0.42, row - 0.42),
                    0.84,
                    0.84,
                    facecolor=face,
                    edgecolor="#64748b",
                    linewidth=1.2,
                    zorder=1,
                )
            )
            text_color = COLOR_WARN if code in {"FP", "FN"} else "#0f172a"
            ax.text(
                col,
                row - 0.12,
                str(value),
                ha="center",
                va="center",
                fontsize=24,
                fontweight="bold",
                color=text_color,
                zorder=2,
            )
            ax.text(
                col,
                row + 0.08,
                f"{code} · {_pct(value, row_total)} строки",
                ha="center",
                va="center",
                fontsize=9,
                color=text_color,
                zorder=2,
            )
            ax.text(
                col,
                row + 0.22,
                captions[row][col],
                ha="center",
                va="center",
                fontsize=9,
                color="#475569",
                zorder=2,
            )

    ax.set_title(
        f"Матрица ошибок RuEcom-2026 (порог {_comma(thr)})\n"
        f"Точность {_comma(precision, 3)} · Полнота {_comma(recall, 3)} · F1 {_comma(f1, 3)}",
        fontsize=12,
        pad=12,
    )
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    _save_fig(fig, out_path, plt)


def render_metrics_vs_threshold(
    rows: list[ThresholdRow], best_threshold: float, out_path: Path, plt: Any
) -> None:
    """Строит зависимость P/R/F1 от порога с отметкой рабочей точки."""
    xs = [r.threshold for r in rows]
    op = _operating_row(rows, best_threshold)

    fig, ax = _new_axes(plt, (10.0, 5.6))
    ax.plot(xs, [r.precision for r in rows], color=COLOR_PRIMARY, linewidth=2.2, label="Точность")
    ax.plot(xs, [r.recall for r in rows], color=COLOR_ACCENT, linewidth=2.2, label="Полнота")
    ax.plot(xs, [r.f1 for r in rows], color=COLOR_WARN, linewidth=2.2, label="F1")
    ax.axvline(best_threshold, color=COLOR_NEUTRAL, linestyle="--", linewidth=1.3, alpha=0.85)
    ax.scatter(
        [op.threshold],
        [op.f1],
        s=90,
        color=COLOR_WARN,
        edgecolors="#0f172a",
        linewidths=0.8,
        zorder=5,
        label=f"макс. F1 при пороге {_comma(op.threshold)}",
    )
    ax.annotate(
        f"P={_comma(op.precision, 3)}\nR={_comma(op.recall, 3)}\nF1={_comma(op.f1, 3)}",
        xy=(op.threshold, op.f1),
        xytext=(op.threshold + 0.12, op.f1 - 0.18),
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": COLOR_GRID},
        arrowprops={"arrowstyle": "->", "color": COLOR_NEUTRAL, "lw": 1.0},
    )
    ax.set_xlabel("Порог принятия решения (оценка сходства наименований)")
    ax.set_ylabel("Значение метрики")
    ax.set_ylim(0, 1.02)
    ax.set_xlim(0, 1.0)
    ax.set_title("Зависимость точности, полноты и F1 от порога (RuEcom-2026)", pad=10)
    ax.legend(loc="lower left", fontsize=9, ncol=2)
    fig.tight_layout()
    _save_fig(fig, out_path, plt)


def render_roc_pr(
    rows: list[ThresholdRow], ext: dict[str, Any], best_threshold: float, out_path: Path, plt: Any
) -> None:
    """Строит ROC- и PR-кривые с базовой линией и подписью рабочей точки."""
    fpr = [r.fp / r.negatives if r.negatives else 0.0 for r in rows]
    tpr = [r.tp / r.positives if r.positives else 0.0 for r in rows]
    rec = [r.recall for r in rows]
    prec = [r.precision for r in rows]
    roc_auc = float(ext.get("roc_auc", 0.0))
    pr_auc = float(ext.get("pr_auc", 0.0))
    op = _operating_row(rows, best_threshold)
    op_fpr = op.fp / op.negatives if op.negatives else 0.0
    op_tpr = op.tp / op.positives if op.positives else 0.0
    baseline_pr = op.positives / (op.positives + op.negatives) if (op.positives + op.negatives) else 0.0

    fig, (ax_roc, ax_pr) = plt.subplots(1, 2, figsize=(11.8, 5.4))
    for ax in (ax_roc, ax_pr):
        ax.set_axisbelow(True)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)

    ax_roc.plot(fpr, tpr, color=COLOR_PRIMARY, linewidth=2.2, label="ROC")
    ax_roc.plot([0, 1], [0, 1], color=COLOR_NEUTRAL, linestyle=":", linewidth=1.1, label="случайный классификатор")
    ax_roc.scatter([op_fpr], [op_tpr], s=80, color=COLOR_WARN, edgecolors="#0f172a", linewidths=0.8, zorder=5)
    ax_roc.annotate(
        f"порог {_comma(best_threshold)}\nTPR={_comma(op_tpr, 3)}",
        xy=(op_fpr, op_tpr),
        xytext=(min(op_fpr + 0.18, 0.72), max(op_tpr - 0.22, 0.12)),
        fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": COLOR_GRID},
        arrowprops={"arrowstyle": "->", "color": COLOR_NEUTRAL, "lw": 0.9},
    )
    ax_roc.set_xlabel("Доля ложных срабатываний (FPR)")
    ax_roc.set_ylabel("Доля верных совпадений (TPR)")
    ax_roc.set_title(f"ROC-кривая · AUC = {_comma(roc_auc, 3)}", fontsize=12)
    ax_roc.legend(loc="lower right", fontsize=8.5)

    ax_pr.plot(rec, prec, color=COLOR_ACCENT, linewidth=2.2, label="PR")
    ax_pr.axhline(baseline_pr, color=COLOR_NEUTRAL, linestyle=":", linewidth=1.1,
                  label=f"базовая точность {_comma(baseline_pr, 3)}")
    ax_pr.scatter([op.recall], [op.precision], s=80, color=COLOR_WARN, edgecolors="#0f172a", linewidths=0.8, zorder=5)
    ax_pr.annotate(
        f"порог {_comma(best_threshold)}\nP={_comma(op.precision, 3)}",
        xy=(op.recall, op.precision),
        xytext=(max(op.recall - 0.38, 0.05), min(op.precision + 0.22, 0.92)),
        fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": COLOR_GRID},
        arrowprops={"arrowstyle": "->", "color": COLOR_NEUTRAL, "lw": 0.9},
    )
    ax_pr.set_xlabel("Полнота (Recall)")
    ax_pr.set_ylabel("Точность (Precision)")
    ax_pr.set_title(f"PR-кривая · AUC = {_comma(pr_auc, 3)}", fontsize=12)
    ax_pr.legend(loc="upper right", fontsize=8.5)

    fig.suptitle("Интегральные характеристики ранжирования (RuEcom-2026)", fontsize=13, y=1.02)
    fig.tight_layout()
    _save_fig(fig, out_path, plt)


def render_score_distribution(
    matches: list[float], nonmatches: list[float], best_threshold: float, out_path: Path, plt: Any
) -> None:
    """Строит распределение оценок с зонами перекрытия и операционной «серой зоной»."""
    fig, ax = _new_axes(plt, (10.2, 5.8))
    bins = [i / 40 for i in range(41)]
    ax.hist(
        nonmatches,
        bins=bins,
        color=COLOR_WARN,
        alpha=0.72,
        edgecolor="#7f1d1d",
        linewidth=0.35,
        label=f"Различные товары ({len(nonmatches)} пар)",
    )
    ax.hist(
        matches,
        bins=bins,
        color=COLOR_ACCENT,
        alpha=0.78,
        edgecolor="#14532d",
        linewidth=0.35,
        label=f"Одинаковые товары ({len(matches)} пар)",
    )
    ax.axvspan(0.15, 0.45, color=COLOR_OVERLAP, alpha=0.14, label="перекрытие 0,15–0,45")
    ax.axvspan(0.25, 0.50, color=COLOR_NEUTRAL, alpha=0.18, label="операционная зона 0,25–0,50")
    ax.axvline(best_threshold, color=COLOR_PRIMARY, linestyle="--", linewidth=1.8,
               label=f"рабочий порог {_comma(best_threshold)}")
    ax.set_xlabel("Оценка сходства наименований")
    ax.set_ylabel("Число пар")
    ax.set_xlim(0, 1.0)
    ax.set_title("Распределение оценки сходства по классам (RuEcom-2026)", pad=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=9)
    fig.subplots_adjust(bottom=0.22)
    _save_fig(fig, out_path, plt)


def render_domain_specificity(
    summary: dict[str, Any], electric: dict[str, Any], out_path: Path, plt: Any
) -> None:
    """Сравнивает специфичность на отрицательных парах общего и EKF-суббенчмарка."""
    best = summary["best_f1"]
    tn, fp = int(best["tn"]), int(best["fp"])
    spec_all = tn / (tn + fp) if (tn + fp) else 0.0

    el = electric["best_f1"]
    el_tn, el_fp = int(el["tn"]), int(el["fp"])
    spec_el = el_tn / (el_tn + el_fp) if (el_tn + el_fp) else 0.0
    el_neg = int(electric.get("negative_pairs", el_tn + el_fp))

    labels = ["Общий набор\nотрицательных пар", "Жёсткие негативы\nодного бренда EKF"]
    values = [spec_all, spec_el]
    fig, ax = _new_axes(plt, (9.0, 5.4))
    bars = ax.bar(labels, values, color=[COLOR_PRIMARY, COLOR_WARN], width=0.52, edgecolor="#334155", linewidth=0.8)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Специфичность (доля верно распознанных различий)")
    ax.set_title("Доменная сложность: похожие товары одного бренда", pad=10)

    detail = [
        f"TN={tn}, FP={fp} из {tn + fp}",
        f"TN={el_tn}, FP={el_fp} из {el_neg}",
    ]
    for bar, value, note in zip(bars, values, detail, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.04,
            f"{_comma(value * 100, 1)}%",
            ha="center",
            fontsize=13,
            fontweight="bold",
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.02,
            note,
            ha="center",
            va="bottom",
            fontsize=9,
            color="#475569",
        )
    fig.tight_layout()
    _save_fig(fig, out_path, plt)


def render_gray_zone(gray: dict[str, Any], out_path: Path, plt: Any) -> None:
    """Показывает состав операционной «серой зоны» и точность среди предсказанных совпадений."""
    base = gray["baseline"]
    tp, fp, tn, fn = int(base["tp"]), int(base["fp"]), int(base["tn"]), int(base["fn"])
    precision = float(base["precision"])
    total = int(gray.get("n_pairs_in_gray_zone", tp + fp + tn + fn))
    predicted_pos = tp + fp

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(11.6, 5.2), gridspec_kw={"width_ratios": [1.15, 1]})

    # Левая панель: среди пар, отнесённых к «совпадению» в серой зоне.
    ax_left.barh(["Предсказано\n«совпадение»"], [tp], color=COLOR_ACCENT, height=0.45, label="верно (TP)")
    ax_left.barh(["Предсказано\n«совпадение»"], [fp], left=[tp], color=COLOR_WARN, height=0.45, label="ошибочно (FP)")
    ax_left.set_xlim(0, max(predicted_pos, 1) * 1.12)
    ax_left.set_xlabel("Число пар в операционной зоне 0,25–0,50")
    ax_left.set_title(f"Среди {predicted_pos} предсказанных совпадений", fontsize=11)
    ax_left.text(
        tp / 2,
        0,
        str(tp),
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color="#0f172a",
    )
    ax_left.text(
        tp + fp / 2,
        0,
        str(fp),
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color="#0f172a",
    )
    ax_left.text(
        predicted_pos * 0.98,
        0.38,
        f"точность {_comma(precision * 100, 1)}%",
        ha="right",
        fontsize=10,
        fontweight="bold",
        color=COLOR_PRIMARY,
    )

    # Правая панель: остальные исходы в зоне.
    cats = ["Верные\nразличия (TN)", "Пропуски (FN)"]
    vals = [tn, fn]
    colors = [COLOR_PRIMARY, COLOR_NEUTRAL]
    bars = ax_right.bar(cats, vals, color=colors, width=0.55, edgecolor="#334155", linewidth=0.8)
    ax_right.set_ylabel("Число пар")
    ax_right.set_title("Предсказано «различие»", fontsize=11)
    ymax = max(vals) * 1.25 if max(vals) else 1
    ax_right.set_ylim(0, ymax)
    for bar, value in zip(bars, vals, strict=True):
        ax_right.text(
            bar.get_x() + bar.get_width() / 2,
            value + ymax * 0.03,
            str(value),
            ha="center",
            fontsize=12,
            fontweight="bold",
        )

    for ax in (ax_left, ax_right):
        ax.set_axisbelow(True)
        ax.grid(True, axis="x" if ax is ax_left else "y", color=COLOR_GRID, alpha=0.5)

    fig.suptitle(
        f"Операционная «серая зона» (0,25–0,50): всего {total} пар",
        fontsize=13,
        y=1.02,
    )
    fig.text(
        0.5,
        0.01,
        "Второй уровень (LLM-валидация) — опциональный фильтр спорных пар; "
        "в контрольном прогоне внешний сервис не вызывался (api_calls = 0).",
        ha="center",
        fontsize=9,
        color=COLOR_NEUTRAL,
    )
    handles, labels = ax_left.get_legend_handles_labels()
    ax_left.legend(handles, labels, loc="lower right", fontsize=8.5)
    fig.subplots_adjust(bottom=0.14)
    fig.tight_layout()
    _save_fig(fig, out_path, plt)


def build_all(bench_dir: Path, electric_dir: Path, out_dir: Path) -> list[Path]:
    """Строит весь набор иллюстраций главы 3 из реальных артефактов."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _apply_vkr_style(plt)

    summary = _read_json(bench_dir / "summary.json")
    ext = _read_json(bench_dir / "extended_metrics.json")
    gray = _read_json(bench_dir / "gemini_gray_zone.json")
    electric = _read_json(electric_dir / "summary.json")
    rows = _read_metrics_csv(bench_dir / "metrics.csv")
    matches, nonmatches = _read_scores_by_label(bench_dir / "pairs.csv")
    best_threshold = float(summary["best_f1"]["threshold"])

    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for name, renderer, args in (
        ("ch3_confusion_matrix.png", render_confusion_matrix, (summary,)),
        ("ch3_metrics_vs_threshold.png", render_metrics_vs_threshold, (rows, best_threshold)),
        ("ch3_roc_pr.png", render_roc_pr, (rows, ext, best_threshold)),
        ("ch3_domain_specificity.png", render_domain_specificity, (summary, electric)),
        ("ch3_gray_zone.png", render_gray_zone, (gray,)),
    ):
        p = out_dir / name
        renderer(*args, p, plt)
        created.append(p)

    if matches and nonmatches:
        p = out_dir / "ch3_score_distribution.png"
        render_score_distribution(matches, nonmatches, best_threshold, p, plt)
        created.append(p)

    return created


def main() -> int:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-dir", type=Path, default=Path("artifacts/ru_benchmark"))
    parser.add_argument("--electric-dir", type=Path, default=Path("artifacts/ru_benchmark_electric"))
    parser.add_argument("--out-dir", type=Path, default=Path("assets/screenshots"))
    args = parser.parse_args()

    try:
        created = build_all(args.bench_dir, args.electric_dir, args.out_dir)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        logger.error("Ошибка построения иллюстраций главы 3: %s", exc)
        return 1

    logger.info("Готово, создано файлов: %d", len(created))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
