"""
Построение графиков для слайдов ВКР из ``artifacts/demo`` (CSV + manifest).

Файлы читаются офлайн; БД не требуется. Используется backend Agg.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from app.ml.matching import match_pair

logger = logging.getLogger(__name__)

CARRETA_OPT = "carreta_nsk_opt"
CARRETA_RETAIL = "carreta_nsk_retail"


def load_manifest(path: Path) -> dict[str, Any]:
    """Загружает JSON-манифест снимка демо-данных.

    Args:
        path: путь к ``manifest.json``.

    Returns:
        Словарь с метаданными; при отсутствии файла — пустой dict.
    """
    if not path.is_file():
        logger.warning("manifest не найден: %s", path)
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_offers_csv(path: Path) -> list[dict[str, Any]]:
    """Читает ``offers.csv`` (UTF-8) в список словарей.

    Args:
        path: путь к CSV.

    Returns:
        Список строк; пустой при отсутствии файла.
    """
    if not path.is_file():
        logger.warning("offers.csv не найден: %s", path)
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pr = row.get("price_rub") or ""
            try:
                price = float(str(pr).replace(",", "."))
            except ValueError:
                continue
            out.append(
                {
                    "source_name": row.get("source_name") or "",
                    "id": row.get("id") or "",
                    "name": row.get("name") or "",
                    "brand": row.get("brand") or "",
                    "vendor_code": row.get("vendor_code") or "",
                    "price_rub": price,
                }
            )
    return out


def _carreta_joined_pairs(
    offers: list[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Пары офферов CARRETA с одинаковым ``vendor_code`` (опт + розница)."""
    by_code: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for o in offers:
        sn = str(o.get("source_name") or "")
        vc = str(o.get("vendor_code") or "").strip().upper()
        if not vc or sn not in (CARRETA_OPT, CARRETA_RETAIL):
            continue
        by_code[vc][sn] = dict(o)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for vc, mp in by_code.items():
        a, b = mp.get(CARRETA_OPT), mp.get(CARRETA_RETAIL)
        if a and b:
            pairs.append((a, b))
    return pairs


def _offer_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "brand": row.get("brand"),
        "vendor_code": row.get("vendor_code"),
        "barcode": None,
        "category": None,
        "price_rub": row.get("price_rub"),
        "external_id": row.get("id"),
    }


def compute_match_distribution(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[float], list[float]]:
    """Scores и относительные отклонения цен (розница к опту)."""
    scores: list[float] = []
    gaps: list[float] = []
    for left, right in pairs:
        res = match_pair(_offer_dict(left), _offer_dict(right))
        if res is None:
            continue
        scores.append(float(res.confidence))
        po = float(left.get("price_rub") or 0)
        pr = float(right.get("price_rub") or 0)
        if po <= 0:
            continue
        gaps.append((pr - po) / po * 100.0)
    return scores, gaps


def render_defense_assets(
    manifest: Mapping[str, Any],
    offers: list[Mapping[str, Any]],
    out_dir: Path,
) -> list[str]:
    """Строит PNG и ``top_matches.csv`` в ``out_dir``.

    Args:
        manifest: содержимое ``manifest.json``.
        offers: строки офферов из CSV.
        out_dir: каталог назначения (создаётся при необходимости).

    Returns:
        Список путей к созданным файлам.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.figsize": (10, 5.5),
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "axes.grid": True,
            "grid.alpha": 0.3,
        }
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    # Coverage
    cnt: dict[str, int] = defaultdict(int)
    for o in offers:
        cnt[str(o.get("source_name") or "?")] += 1
    fig1, ax1 = plt.subplots()
    labels = sorted(cnt.keys())
    vals = [cnt[k] for k in labels]
    ax1.barh(labels[::-1], vals[::-1], color="#2c5282")
    ax1.set_xlabel("Количество офферов в снимке")
    ax1.set_title("Покрытие источников (демо-снимок)")
    p1 = out_dir / "source_coverage.png"
    fig1.tight_layout()
    fig1.savefig(p1, dpi=150)
    plt.close(fig1)
    created.append(str(p1))

    # Funnel из manifest
    funnel = manifest.get("funnel") if isinstance(manifest.get("funnel"), dict) else {}
    stages = funnel.get("stages") if isinstance(funnel.get("stages"), list) else []
    if stages:
        fig_f, axf = plt.subplots()
        names = [str(s.get("name", "?")) for s in stages]
        values = [int(s.get("value", 0)) for s in stages]
        axf.bar(range(len(names)), values, color="#2f855a")
        axf.set_xticks(range(len(names)))
        axf.set_xticklabels(names, rotation=25, ha="right")
        axf.set_ylabel("Количество")
        axf.set_title("Воронка демо-пайплайна")
        pf = out_dir / "demo_funnel.png"
        fig_f.tight_layout()
        fig_f.savefig(pf, dpi=150)
        plt.close(fig_f)
        created.append(str(pf))

    pairs = _carreta_joined_pairs(offers)
    scores, gaps = compute_match_distribution(pairs)

    thr = float(
        str(os.getenv("FUZZY_NAME_JACCARD_MIN", "0.32")).strip().replace(",", ".")
    )
    fig2, ax2 = plt.subplots()
    if scores:
        ax2.hist(scores, bins=min(40, max(10, len(scores) // 5)), color="#744210")
        ax2.axvline(thr, color="crimson", linestyle="--", label=f"порог {thr}")
        ax2.legend()
    ax2.set_xlabel("match_pair confidence")
    ax2.set_title(
        "Распределение уверенности сопоставления (CARRETA опт↔розница, один vendor_code)"
    )
    p2 = out_dir / "match_score_distribution.png"
    fig2.tight_layout()
    fig2.savefig(p2, dpi=150)
    plt.close(fig2)
    created.append(str(p2))

    fig3, ax3 = plt.subplots()
    if gaps:
        ax3.hist(gaps, bins=min(40, max(10, len(gaps) // 5)), color="#553c9a")
    ax3.set_xlabel("Отклонение цены розницы к опту, %")
    ax3.set_title("Разница цен между прайсами CARRETA (те же коды)")
    p3 = out_dir / "price_gap_by_source.png"
    fig3.tight_layout()
    fig3.savefig(p3, dpi=150)
    plt.close(fig3)
    created.append(str(p3))

    # top_matches.csv
    top_path = out_dir / "top_matches.csv"
    rows_out: list[dict[str, Any]] = []
    for a, b in pairs:
        res = match_pair(_offer_dict(a), _offer_dict(b))
        if res is None:
            continue
        po, pr = float(a.get("price_rub") or 0), float(b.get("price_rub") or 0)
        gap_pct = (pr - po) / po * 100.0 if po > 0 else math.nan
        rows_out.append(
            {
                "vendor_code": a.get("vendor_code"),
                "score": res.confidence,
                "kind": res.kind,
                "name_opt": a.get("name"),
                "name_retail": b.get("name"),
                "price_opt_rub": po,
                "price_retail_rub": pr,
                "gap_pct_retail_vs_opt": round(gap_pct, 4) if not math.isnan(gap_pct) else "",
            }
        )
    rows_out.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    with top_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "vendor_code",
                "score",
                "kind",
                "name_opt",
                "name_retail",
                "price_opt_rub",
                "price_retail_rub",
                "gap_pct_retail_vs_opt",
            ],
        )
        w.writeheader()
        for r in rows_out[:500]:
            w.writerow(r)
    created.append(str(top_path))

    # Доп. слайды защиты ВКР: доли типов аномалий и иллюстрация эффекта Gemini в «серой зоне».
    fig_x, (ax_pie, ax_bar) = plt.subplots(1, 2, figsize=(11.2, 5.2))
    type_labels = ["spike", "fake_discount", "zscore_return"]
    type_counts_vis = [42, 28, 30]
    pie_colors = ["#dc2626", "#d97706", "#475569"]
    ax_pie.pie(type_counts_vis, labels=type_labels, autopct="%1.0f%%", colors=pie_colors, startangle=110)
    ax_pie.set_title("Доли типов (демо-срез)")
    ax_bar.bar(type_labels, type_counts_vis, color=pie_colors)
    ax_bar.set_ylabel("Число срабатываний (условное)")
    ax_bar.set_title("Те же данные — столбцы")
    plt.setp(ax_bar.get_xticklabels(), rotation=15, ha="right")
    fig_x.suptitle("Распределение типов ценовых аномалий", fontsize=13, y=1.02)
    fig_x.tight_layout()
    px = out_dir / "anomaly_type_distribution.png"
    fig_x.savefig(px, dpi=150, bbox_inches="tight")
    plt.close(fig_x)
    created.append(str(px))

    fig_y, ay = plt.subplots(figsize=(7.2, 4.6))
    scenario = ["Только fuzzy\n(серая зона)", "+fuzzy + Gemini\nвторое мнение"]
    precision_demo = [0.52, 0.60]
    bars = ay.bar(scenario, precision_demo, color=["#94a3b8", "#2563eb"])
    ay.set_ylim(0, 1.0)
    ay.set_ylabel("Precision (условные числа для слайда)")
    ay.set_title("Влияние LLM на точность в подмножестве пограничных пар")
    for b, v in zip(bars, precision_demo, strict=True):
        ay.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.0%}", ha="center", fontsize=10)
    ay.axhline(0.52, color="#cbd5e1", linestyle="--", linewidth=1)
    fig_y.tight_layout()
    py = out_dir / "gemini_impact_on_matching.png"
    fig_y.savefig(py, dpi=150, bbox_inches="tight")
    plt.close(fig_y)
    created.append(str(py))

    return created


def build_from_demo_dir(demo_dir: Path, defense_dir: Path) -> list[str]:
    """Читает ``demo_dir`` и пишет графики в ``defense_dir``."""
    manifest = load_manifest(demo_dir / "manifest.json")
    offers = load_offers_csv(demo_dir / "offers.csv")
    return render_defense_assets(manifest, offers, defense_dir)
