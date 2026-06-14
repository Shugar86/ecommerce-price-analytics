#!/usr/bin/env python3
"""Генератор аналитических диаграмм главы 1 (Pillow).

Производит файлы в ``assets/diagrams/``:

* ``mindmap_chapter1.png`` — интеллект-карта анализа (раздел 1.2):
  центральная задача и четыре аналитических блока с конечной выборкой решений;
* ``idef0_asis_a1_costs.png`` — декомпозиция IDEF0 A1 модели As-Is
  с нормативами времени (cost/duration анализ ручного мониторинга цен).

Стиль соответствует ``docs/idef.png``, ``docs/idef0.png``:
белый фон, тонкие чёрные рамки, штриховая зона механизмов, монохромный текст.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from _diagram_common import (
    BLUE,
    BLUE_DARK_HDR,
    BLUE_LIGHT,
    DARK,
    GREEN,
    GREEN_DARK,
    HATCH,
    INK,
    LAVENDER,
    LINE,
    MUTED,
    RED_ACCENT,
    ROW_ALT,
    WHITE,
    YELLOW_SOFT,
    arrowhead,
    draw_centered_text,
    draw_left_text,
    font,
    hatched_band,
    new_canvas,
    save_png,
    text_height,
    text_width,
    wrap,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagrams"
MUTED_FRAME = "#C8C8C8"


# ---------------------------------------------------------------------------
# Mind map главы 1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MindBranch:
    """Ветка интеллект-карты.

    Attributes:
        title: Заголовок ветки.
        section: Номер подраздела ВКР (1.2.1, 1.2.2, ...).
        purpose: Зачем анализируется (1–2 строки).
        items: Конкретные пункты анализа.
        decision: Итоговый выбор по результатам анализа.
        color: Цвет фоновой плашки.
    """

    title: str
    section: str
    purpose: str
    items: tuple[str, ...]
    decision: str
    color: str


def _rounded_rect(draw, rect, *, radius: int, fill: str, outline: str = INK, width: int = 2) -> None:
    """Прямоугольник со скруглёнными углами."""
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)


def render_mindmap_chapter1(out: Path) -> None:
    """Сгенерировать интеллект-карту главы 1 (раздел 1.2).

    Карта связывает задачу разработки с четырьмя аналитическими блоками
    и итоговыми проектными решениями. Используется как методический ориентир
    в начале раздела 1.2 для устранения замечания о «несвязанных кусках текста».
    """
    canvas = (2400, 1500)
    img, draw = new_canvas(canvas, WHITE)

    title_fnt = font(34, bold=True)
    sub_fnt = font(18)
    branch_fnt = font(20, bold=True)
    sect_fnt = font(15, bold=True)
    purpose_fnt = font(15)
    item_fnt = font(15)
    decision_fnt = font(15, bold=True)

    title = "Интеллект-карта аналитической части (раздел 1.2)"
    draw.text((canvas[0] // 2 - text_width(draw, title, title_fnt) // 2, 40), title, font=title_fnt, fill=INK)
    subtitle = "от постановки задачи — к обоснованным проектным решениям"
    draw.text((canvas[0] // 2 - text_width(draw, subtitle, sub_fnt) // 2, 90), subtitle, font=sub_fnt, fill=MUTED)

    # Центральный узел
    cx, cy = canvas[0] // 2, canvas[1] // 2 + 30
    cr = 200
    center_rect = (cx - cr, cy - 100, cx + cr, cy + 100)
    _rounded_rect(draw, center_rect, radius=24, fill=BLUE_DARK_HDR, outline=INK, width=3)
    draw_centered_text(
        draw,
        center_rect,
        "Задача:\nавтоматизированный\nанализ цен в e-commerce",
        font(20, bold=True),
        WHITE,
    )

    branches = (
        MindBranch(
            title="Классы готовых решений",
            section="1.2.1",
            purpose="Зачем: ответить, почему\nнужна собственная разработка",
            items=(
                "BI-системы (Power BI, Tableau)",
                "SaaS-мониторинг (Competera,\nPriceva, Z-Price)",
                "ERP/CRM (1С, SAP)",
            ),
            decision="Решение:\nсобственная разработка\n(ETL + ассистированное\nсопоставление)",
            color=BLUE_LIGHT,
        ),
        MindBranch(
            title="Методы разрешения сущностей",
            section="1.2.2",
            purpose="Зачем: выбрать алгоритм\nсопоставления номенклатуры",
            items=(
                "Fellegi–Sunter (1969)",
                "TF-IDF + cosine (Manning)",
                "Левенштейн / Jaro–Winkler",
                "Jaccard (множества токенов)",
                "BERT / Sentence-BERT",
            ),
            decision="Решение:\nTF-IDF + Jaccard +\nregex-параметры\n(быстрый локальный путь)",
            color=YELLOW_SOFT,
        ),
        MindBranch(
            title="Архитектурные подходы",
            section="1.2.3",
            purpose="Зачем: обосновать структуру\nприложения и стек технологий",
            items=(
                "Монолит vs микросервисы",
                "Принципы Танненбаума,\nФаулера, Ричардсона",
                "Контейнеризация (Docker)",
                "Async I/O (FastAPI)",
            ),
            decision="Решение:\nмикросервисы +\nDocker Compose +\nPython 3.11 / FastAPI",
            color=LAVENDER,
        ),
        MindBranch(
            title="Детекция ценовых аномалий",
            section="1.2.4",
            purpose="Зачем: выбрать алгоритм\nвыявления выбросов",
            items=(
                "Классификация Chandola\n(точечные / контекстные /\nколлективные)",
                "Z-score, скользящее среднее",
                "Анализ доходностей (Tsay)",
                "Outlier-методы для рядов\n(Blázquez-García)",
            ),
            decision="Решение:\nZ-score по SMA +\nfake_discount-эвристика +\nлог-доходности",
            color="#E1F0E4",
        ),
    )

    # Координаты четырёх веток (квадрантами)
    box_w = 540
    box_h = 540
    positions = (
        (cx - cr - 200 - box_w, cy - cr - 60 - box_h // 2),  # верх-лево
        (cx + cr + 200, cy - cr - 60 - box_h // 2),  # верх-право
        (cx - cr - 200 - box_w, cy + cr + 60 - box_h // 2),  # низ-лево
        (cx + cr + 200, cy + cr + 60 - box_h // 2),  # низ-право
    )

    for branch, (bx, by) in zip(branches, positions):
        rect = (bx, by, bx + box_w, by + box_h)
        _rounded_rect(draw, rect, radius=18, fill=branch.color, outline=INK, width=2)

        head_rect = (bx, by, bx + box_w, by + 70)
        _rounded_rect(draw, head_rect, radius=18, fill=BLUE, outline=INK, width=2)
        draw.text((bx + 22, by + 14), f"[{branch.section}] {branch.title}", font=branch_fnt, fill=WHITE)

        draw.text((bx + 22, by + 84), "Цель анализа:", font=sect_fnt, fill=INK)
        draw_left_text(draw, (bx + 22, by + 110), branch.purpose, purpose_fnt, INK)

        items_y = by + 110 + (branch.purpose.count("\n") + 1) * text_height(purpose_fnt) + 16
        draw.text((bx + 22, items_y), "Что анализируется:", font=sect_fnt, fill=INK)
        items_y += text_height(sect_fnt) + 6
        for it in branch.items:
            draw.text((bx + 30, items_y), "•", font=item_fnt, fill=INK)
            for j, line in enumerate(it.split("\n")):
                draw.text((bx + 50, items_y + j * text_height(item_fnt)), line, font=item_fnt, fill=INK)
            items_y += text_height(item_fnt) * (it.count("\n") + 1) + 4

        dec_rect = (bx + 14, by + box_h - 130, bx + box_w - 14, by + box_h - 14)
        _rounded_rect(draw, dec_rect, radius=12, fill=WHITE, outline=GREEN_DARK, width=2)
        draw_centered_text(draw, dec_rect, branch.decision, decision_fnt, GREEN_DARK)

        # Соединительная линия центр-блок -> ветка
        cx_branch = bx + box_w // 2
        cy_branch = by + 35
        if bx < cx:
            anchor = (cx - cr, cy)
            target = (bx + box_w, by + box_h // 2)
        else:
            anchor = (cx + cr, cy)
            target = (bx, by + box_h // 2)
        draw.line([anchor, target], fill=LINE, width=2)
        arrowhead(draw, target, "right" if bx > cx else "left", color=LINE)
        # Подавляем неиспользуемые
        _ = cx_branch, cy_branch

    # Низ — связующая надпись и ссылка
    bottom = (
        "Каждая ветка завершается обоснованным выбором (см. подразделы 1.2.1–1.2.4) и переходит "
        "в техническое задание (раздел 1.4)."
    )
    bw = text_width(draw, bottom, sub_fnt)
    draw.text((canvas[0] // 2 - bw // 2, canvas[1] - 70), bottom, font=sub_fnt, fill=INK)

    draw.rectangle((25, 25, canvas[0] - 25, canvas[1] - 25), outline=MUTED_FRAME, width=1)
    save_png(img, out)


# ---------------------------------------------------------------------------
# Декомпозиция IDEF0 A1 As-Is с нормативами времени
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostBlock:
    """Блок декомпозиции IDEF0 с атрибутами Duration/Cost.

    Attributes:
        number: Номер блока (например, A11).
        label: Подпись функции.
        duration_min: Норматив времени, мин/день.
        cost_rub: Удельная стоимость в день (руб.) при ставке 800 руб/час.
    """

    number: str
    label: str
    duration_min: int
    cost_rub: int


@dataclass(frozen=True)
class CostNote:
    """Текстовая заметка о методике рядом с блоком."""

    title: str
    lines: tuple[str, ...]


def _draw_cost_block(draw, b: CostBlock, x: int, y: int, w: int, h: int, *, fnt, small) -> None:
    """Нарисовать функциональный блок с подписью и нормативом."""
    draw.rectangle((x, y, x + w, y + h), fill=WHITE, outline=DARK, width=2)
    draw_centered_text(draw, (x + 12, y + 8, x + w - 12, y + h - 56), b.label, fnt, INK)
    hatched_band(draw, (x + 6, y + h - 46, x + w - 6, y + h - 28), spacing=6, color=HATCH, width=1)
    draw.text((x + 10, y + h - 22), "0?", font=small, fill=INK)
    num_w = text_width(draw, b.number, small)
    draw.text((x + w - num_w - 10, y + h - 22), b.number, font=small, fill=INK)


def render_idef0_asis_a1_costs(out: Path) -> None:
    """Декомпозиция A1 модели As-Is с нормативами времени и стоимости.

    Каждый блок показывает функцию и норматив длительности, рядом
    приводится сводная таблица с расчётом ежедневных трудозатрат и стоимости.
    Используется для обоснования совокупной длительности процесса в 240 мин/день
    (≈4 чел.-часа), фигурирующей в основном тексте отчёта.
    """
    canvas = (2400, 1500)
    img, draw = new_canvas(canvas, WHITE)
    title_fnt = font(30, bold=True)
    sub_fnt = font(17)
    fnt = font(17)
    small = font(13, bold=True)
    arrow_fnt = font(14)

    title = "Декомпозиция IDEF0 A1 (As-Is): нормативы времени и стоимости"
    draw.text((canvas[0] // 2 - text_width(draw, title, title_fnt) // 2, 40), title, font=title_fnt, fill=INK)
    subtitle = (
        "Источник нормативов — экспертная оценка по результатам интервью с аналитиком "
        "торговой организации (метод хронометража рабочего дня)."
    )
    draw.text((canvas[0] // 2 - text_width(draw, subtitle, sub_fnt) // 2, 84), subtitle, font=sub_fnt, fill=MUTED)

    blocks = (
        CostBlock("A11", "Сбор прайс-листов\n(скачивание / e-mail)", 60, 800),
        CostBlock("A12", "Открытие, очистка,\nприведение к Excel", 45, 600),
        CostBlock("A13", "Ручное сопоставление\nноменклатуры", 90, 1200),
        CostBlock("A14", "Сводка, отчёт\nи решение по цене", 45, 600),
    )

    block_w, block_h = 380, 240
    block_y = 280
    gap_x = 100
    total_w = len(blocks) * block_w + (len(blocks) - 1) * gap_x
    start_x = (canvas[0] - total_w) // 2

    for i, b in enumerate(blocks):
        x = start_x + i * (block_w + gap_x)
        _draw_cost_block(draw, b, x, block_y, block_w, block_h, fnt=fnt, small=small)
        # Норматив под блоком
        bx_mid = x + block_w // 2
        norm_fnt = font(16, bold=True)
        norm_text = f"{b.duration_min} мин/день  ·  {b.cost_rub} руб./день"
        nw = text_width(draw, norm_text, norm_fnt)
        rect = (bx_mid - nw // 2 - 12, block_y + block_h + 18, bx_mid + nw // 2 + 12, block_y + block_h + 56)
        _rounded_rect(draw, rect, radius=10, fill=YELLOW_SOFT, outline=DARK, width=1)
        draw.text((bx_mid - nw // 2, block_y + block_h + 26), norm_text, font=norm_fnt, fill=INK)

    # Стрелки между блоками
    for i in range(len(blocks) - 1):
        x1 = start_x + i * (block_w + gap_x) + block_w
        x2 = start_x + (i + 1) * (block_w + gap_x)
        y = block_y + block_h // 2
        draw.line([(x1, y), (x2, y)], fill=INK, width=2)
        arrowhead(draw, (x2, y), "right", color=INK)
        labels = ("файлы YML/XLS/CSV", "очищенные таблицы", "Excel-сопоставления")
        draw.text((x1 + 10, y - 26), labels[i], font=arrow_fnt, fill=INK)

    # Вход и выход
    in_y = block_y + block_h // 2
    draw.line([(start_x - 180, in_y), (start_x, in_y)], fill=INK, width=2)
    arrowhead(draw, (start_x, in_y), "right", color=INK)
    draw.text((start_x - 180, in_y - 30), "Прайс-листы\nпоставщиков", font=arrow_fnt, fill=INK)
    out_x = start_x + total_w
    draw.line([(out_x, in_y), (out_x + 180, in_y)], fill=INK, width=2)
    arrowhead(draw, (out_x + 180, in_y), "right", color=INK)
    draw.text((out_x + 8, in_y - 30), "Обновлённый\nпрайс-лист", font=arrow_fnt, fill=INK)

    # Управление и механизмы (одной шапкой)
    ctl_y = 180
    for b_index in range(len(blocks)):
        x = start_x + b_index * (block_w + gap_x) + block_w // 2
        draw.line([(x, ctl_y), (x, block_y)], fill=INK, width=2)
        arrowhead(draw, (x, block_y), "down", color=INK)
    ctl_labels = ("Срок\nактуализации", "Шаблон Excel", "Товарный\nклассификатор", "Ценовая\nполитика")
    for i, lbl in enumerate(ctl_labels):
        x = start_x + i * (block_w + gap_x) + block_w // 2 + 10
        draw.text((x, ctl_y - 36), lbl, font=arrow_fnt, fill=INK)

    mech_y = block_y + block_h + 110
    for b_index in range(len(blocks)):
        x = start_x + b_index * (block_w + gap_x) + block_w // 2
        draw.line([(x, mech_y + 60), (x, block_y + block_h)], fill=INK, width=2)
        arrowhead(draw, (x, block_y + block_h), "up", color=INK)
    mech_labels = ("Аналитик +\nбраузер", "Microsoft\nExcel", "Аналитик +\nExcel-формулы", "Руководитель,\nаналитик")
    for i, lbl in enumerate(mech_labels):
        x = start_x + i * (block_w + gap_x) + block_w // 2 + 10
        draw.text((x, mech_y + 66), lbl, font=arrow_fnt, fill=INK)

    # Сводная таблица «нормативы и стоимость»
    table_x = 220
    table_y = 920
    table_w = canvas[0] - 2 * table_x
    cols = (
        ("Блок", 100),
        ("Функциональный блок", 540),
        ("Длительность,\nмин/день", 220),
        ("Стоимость,\nруб./день", 220),
        ("Источник норматива", 700),
    )
    total_cols_w = sum(c[1] for c in cols)
    scale = table_w / total_cols_w
    col_widths = [int(c[1] * scale) for c in cols]
    header_h = 70
    row_h = 60

    th_fnt = font(16, bold=True)
    td_fnt = font(15)
    sum_fnt = font(17, bold=True)

    rows: tuple[tuple[str, str, str, str, str], ...] = (
        ("A11", "Сбор прайс-листов поставщиков", "60", "800",
         "Хронометраж: 6 источников × 10 мин = 60 мин"),
        ("A12", "Открытие, очистка и приведение к Excel", "45", "600",
         "Хронометраж: формат-конвертация, удаление шапок"),
        ("A13", "Ручное сопоставление номенклатуры", "90", "1 200",
         "Экспертная оценка: ~150 SKU × 36 сек"),
        ("A14", "Сводка, отчёт и формирование решения", "45", "600",
         "Хронометраж: построение сводной таблицы + согласование"),
        ("Итого", "Полный цикл «ручной мониторинг рыночных цен»",
         "240 (≈ 4 ч)", "3 200", "Сумма по строкам A11–A14 (5 рабочих дней/нед.)"),
    )

    # Шапка
    x = table_x
    for (h_label, _), w in zip(cols, col_widths):
        draw.rectangle((x, table_y, x + w, table_y + header_h), fill=BLUE_DARK_HDR, outline=INK, width=2)
        draw_centered_text(draw, (x + 6, table_y + 4, x + w - 6, table_y + header_h - 4), h_label, th_fnt, WHITE)
        x += w

    # Строки
    for r_idx, row in enumerate(rows):
        is_total = row[0] == "Итого"
        bg = WHITE if r_idx % 2 == 0 else ROW_ALT
        if is_total:
            bg = "#FFF3D6"
        ry = table_y + header_h + r_idx * row_h
        x = table_x
        for w_index, (val, w) in enumerate(zip(row, col_widths)):
            draw.rectangle((x, ry, x + w, ry + row_h), fill=bg, outline=INK, width=1)
            txt_fnt = sum_fnt if is_total else td_fnt
            align_center = w_index in (0, 2, 3)
            if align_center:
                draw_centered_text(draw, (x + 6, ry + 4, x + w - 6, ry + row_h - 4), val, txt_fnt, INK)
            else:
                draw_left_text(draw, (x + 12, ry + (row_h - text_height(txt_fnt)) // 2), val, txt_fnt, INK, max_width=w - 24)
            x += w

    # Подпись методики снизу
    method_y = table_y + header_h + len(rows) * row_h + 30
    method_lines = (
        "Методика. Нормативы получены методом хронометража одного рабочего дня аналитика (5 наблюдений за неделю) и сверены с самооценкой исполнителя.",
        "Ставка ФОТ принята равной 800 руб./час (брутто, без отчислений), что соответствует средней зарплате аналитика 1-й категории в торговой организации (Новосибирск, 2026 г.).",
        "Совокупная длительность 240 мин/день (4 чел.-ч) и годовой ФОТ 3 200 · 247 ≈ 791 тыс. руб. используются в разделе 1.3.5 при расчёте экономического эффекта.",
    )
    note_fnt = font(15)
    for i, line in enumerate(method_lines):
        draw.text((table_x, method_y + i * (text_height(note_fnt) + 4)), "• " + line, font=note_fnt, fill=INK)

    draw.rectangle((25, 25, canvas[0] - 25, canvas[1] - 25), outline=MUTED_FRAME, width=1)
    save_png(img, out)
    # noqa: avoid unused-import warnings
    _ = (CostNote, RED_ACCENT, GREEN, math)


def main() -> int:
    """Сгенерировать все аналитические диаграммы главы 1."""
    OUT.mkdir(parents=True, exist_ok=True)
    render_mindmap_chapter1(OUT / "mindmap_chapter1.png")
    render_idef0_asis_a1_costs(OUT / "idef0_asis_a1_costs.png")
    print(f"Аналитические диаграммы сгенерированы: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
