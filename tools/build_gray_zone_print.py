#!/usr/bin/env python3
"""Печатная версия рисунка 3.11 (операционная «серая зона»).

Оптимизации под лазерную/струйную печать:
- более светлые цвета столбцов с чёрными контурами;
- крупный жирный текст внутри/над столбцами;
- чёрные оси, подписи и сноски;
- чисто белый фон без прозрачности.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _comma(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def render(gray_path: Path, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with gray_path.open(encoding="utf-8") as f:
        gray = json.load(f)

    base = gray["baseline"]
    tp, fp, tn, fn = int(base["tp"]), int(base["fp"]), int(base["tn"]), int(base["fn"])
    precision = float(base["precision"])
    total = int(gray.get("n_pairs_in_gray_zone", tp + fp + tn + fn))
    predicted_pos = tp + fp

    # Палитра, устойчивая к затемнению при печати/CMYK и различимая в ЧБ.
    # Grayscale яркости подобраны так, чтобы столбцы не сливались при ЧБ печати.
    COLOR_TP = "#4ade80"  # зелёный, grayscale ~167
    COLOR_FP = "#dc2626"  # тёмно-красный, grayscale ~112 (выделяется)
    COLOR_TN = "#93c5fd"  # светло-синий, grayscale ~200
    COLOR_FN = "#fde047"  # светло-жёлтый, grayscale ~225
    COLOR_TEXT = "#000000"
    COLOR_GRID = "#d1d5db"

    plt.rcParams.update(
        {
            "font.family": ["DejaVu Sans", "sans-serif"],
            "font.size": 13,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "axes.grid": True,
            "grid.alpha": 0.45,
            "grid.color": COLOR_GRID,
            "grid.linewidth": 0.9,
            "axes.edgecolor": COLOR_TEXT,
            "axes.facecolor": "#ffffff",
            "figure.facecolor": "#ffffff",
            "savefig.facecolor": "#ffffff",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.22,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": True,
            "legend.framealpha": 1.0,
            "legend.edgecolor": COLOR_TEXT,
            "legend.fontsize": 12,
        }
    )

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(13.5, 6.0), gridspec_kw={"width_ratios": [1.15, 1]}
    )

    edge_kw = {"edgecolor": COLOR_TEXT, "linewidth": 1.5}

    # Левая панель: stacked bar
    ax_left.barh(
        ["Предсказано\n«совпадение»"],
        [tp],
        color=COLOR_TP,
        height=0.50,
        label="верно (TP)",
        hatch="/",
        **edge_kw,
    )
    ax_left.barh(
        ["Предсказано\n«совпадение»"],
        [fp],
        left=[tp],
        color=COLOR_FP,
        height=0.50,
        label="ошибочно (FP)",
        hatch="\\",
        **edge_kw,
    )
    ax_left.set_xlim(0, max(predicted_pos, 1) * 1.12)
    ax_left.set_xlabel("Число пар в операционной зоне 0,25–0,50", fontsize=14, labelpad=8)
    ax_left.set_title(f"Среди {predicted_pos} предсказанных совпадений", fontsize=15, pad=10)

    ax_left.text(
        tp / 2,
        0,
        str(tp),
        ha="center",
        va="center",
        fontsize=20,
        fontweight="bold",
        color=COLOR_TEXT,
    )
    ax_left.text(
        tp + fp / 2,
        0,
        str(fp),
        ha="center",
        va="center",
        fontsize=20,
        fontweight="bold",
        color=COLOR_TEXT,
    )
    ax_left.text(
        predicted_pos * 0.98,
        0.40,
        f"точность {_comma(precision * 100, 1)}%",
        ha="right",
        fontsize=15,
        fontweight="bold",
        color=COLOR_TEXT,
    )

    # Правая панель: grouped bar
    cats = ["Верные\nразличия (TN)", "Пропуски (FN)"]
    vals = [tn, fn]
    colors = [COLOR_TN, COLOR_FN]
    hatches = ["|", "-"]
    bars = ax_right.bar(cats, vals, color=colors, width=0.55, **edge_kw)
    for bar, hatch in zip(bars, hatches, strict=True):
        bar.set_hatch(hatch)
    ax_right.set_ylabel("Число пар", fontsize=14, labelpad=8)
    ax_right.set_title("Предсказано «различие»", fontsize=15, pad=10)
    ymax = max(vals) * 1.35 if max(vals) else 1
    ax_right.set_ylim(0, ymax)
    for bar, value in zip(bars, vals, strict=True):
        ax_right.text(
            bar.get_x() + bar.get_width() / 2,
            value + ymax * 0.04,
            str(value),
            ha="center",
            fontsize=20,
            fontweight="bold",
            color=COLOR_TEXT,
        )

    for ax in (ax_left, ax_right):
        ax.set_axisbelow(True)
        ax.grid(True, axis="x" if ax is ax_left else "y", color=COLOR_GRID, alpha=0.6)
        ax.tick_params(labelsize=13)
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_color(COLOR_TEXT)

    fig.suptitle(
        f"Операционная «серая зона» (0,25–0,50): всего {total} пар",
        fontsize=18,
        fontweight="bold",
        y=1.02,
        color=COLOR_TEXT,
    )
    fig.text(
        0.5,
        -0.02,
        "Второй уровень (LLM-валидация) — опциональный фильтр спорных пар; "
        "в контрольном прогоне внешний сервис не вызывался (api_calls = 0).",
        ha="center",
        fontsize=12,
        color=COLOR_TEXT,
    )
    handles, labels = ax_left.get_legend_handles_labels()
    ax_left.legend(handles, labels, loc="lower right", fontsize=12, framealpha=1.0)

    fig.subplots_adjust(bottom=0.14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, facecolor="white")
    plt.close(fig)
    print(f"Создан: {out_path}")


def main() -> int:
    if len(sys.argv) >= 3:
        gray_path = Path(sys.argv[1])
        out_path = Path(sys.argv[2])
    else:
        gray_path = Path("artifacts/ru_benchmark/gemini_gray_zone.json")
        out_path = Path("assets/screenshots/ch3_gray_zone_print.png")
    render(gray_path, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
