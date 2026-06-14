#!/usr/bin/env python3
"""Генератор табличной диаграммы Ганта (Pillow).

Производит ``assets/diagrams/gantt_table_style.png`` в стиле образца
``docs/gant.png``: таблица слева, недельная сетка справа, синие бары
для основных этапов и жёлтые — для подзадач/диаграмм. Заголовок группы
тёмно-синий с белым текстом, чередующиеся строки — бледно-голубые.

Источник содержания — ``assets/diagrams/gantt_project_timeline.mmd``;
этапы соответствуют разделу §3.4.2 ВКР.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from _diagram_common import (
    BLUE,
    BLUE_DARK_HDR,
    BLUE_LIGHT,
    GREEN_DARK,
    INK,
    LINE,
    MUTED,
    ROW_ALT,
    WHITE,
    YELLOW,
    font,
    new_canvas,
    save_png,
    text_width,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagrams"

CANVAS = (2400, 1500)


@dataclass
class GanttTask:
    """Строка задачи в диаграмме Ганта.

    Attributes:
        wbs: Номер ИСР (``1.1`` для подзадач, ``1`` для группы).
        name: Название задачи.
        start: Дата начала.
        end: Дата окончания (включительно).
        is_group: True для заголовка группы (рендерится сплошной плашкой).
        bar_color: Цвет полосы (BLUE для этапов, YELLOW для подзадач/диаграмм).
        progress: Процент выполнения (0–100).
    """

    wbs: str
    name: str
    start: date
    end: date
    is_group: bool = False
    bar_color: str = BLUE
    progress: int = 100


@dataclass
class GanttStage:
    """Группа задач (этап разработки).

    Attributes:
        wbs: Номер этапа.
        name: Название этапа.
        tasks: Подзадачи этапа.
    """

    wbs: str
    name: str
    tasks: list[GanttTask] = field(default_factory=list)


PROJECT_START: date = date(2026, 2, 2)
PROJECT_END: date = date(2026, 5, 17)
TOTAL_WEEKS: int = 15


def _duration_days(start: date, end: date) -> int:
    """Длительность в днях, включая граничные даты."""
    return (end - start).days + 1


def stages() -> list[GanttStage]:
    """Сформировать иерархию этапов из содержания ``gantt_project_timeline.mmd``."""
    s1 = GanttStage("1", "Анализ и проектирование")
    s1.tasks = [
        GanttTask("1.1", "Анализ предметной области и постановка задачи", date(2026, 2, 2), date(2026, 2, 11), bar_color=YELLOW),
        GanttTask("1.2", "Проектирование архитектуры и модели данных", date(2026, 2, 12), date(2026, 2, 19), bar_color=YELLOW),
        GanttTask("1.3", "Разработка комплекта UML-диаграмм", date(2026, 2, 9), date(2026, 2, 15), bar_color=YELLOW),
    ]
    s2 = GanttStage("2", "Разработка серверной части")
    s2.tasks = [
        GanttTask("2.1", "Схема БД и миграции Alembic", date(2026, 2, 20), date(2026, 2, 23), bar_color=BLUE),
        GanttTask("2.2", "ETL-конвейер YML / XLS / CSV", date(2026, 2, 24), date(2026, 3, 7), bar_color=BLUE),
        GanttTask("2.3", "Лексическая нормализация наименований", date(2026, 3, 8), date(2026, 3, 13), bar_color=YELLOW),
        GanttTask("2.4", "Идемпотентная запись и история цен", date(2026, 3, 14), date(2026, 3, 17), bar_color=BLUE),
    ]
    s3 = GanttStage("3", "Разработка клиентской части")
    s3.tasks = [
        GanttTask("3.1", "REST API и веб-интерфейс (FastAPI + Jinja2)", date(2026, 3, 10), date(2026, 3, 23), bar_color=BLUE),
        GanttTask("3.2", "Telegram-бот (Aiogram 3)", date(2026, 3, 24), date(2026, 3, 29), bar_color=BLUE),
    ]
    s4 = GanttStage("4", "Интеллектуальный контур")
    s4.tasks = [
        GanttTask("4.1", "Детектор аномалий (Z-score, fake discount)", date(2026, 3, 8), date(2026, 3, 13), bar_color=BLUE),
        GanttTask("4.2", "TF-IDF / Jaccard сопоставление (AI Worker)", date(2026, 3, 14), date(2026, 3, 21), bar_color=BLUE),
        GanttTask("4.3", "Интеграция Gemini 2.5 Flash", date(2026, 3, 22), date(2026, 3, 26), bar_color=YELLOW),
        GanttTask("4.4", "Эталонный набор данных RuEcom-2026", date(2026, 3, 25), date(2026, 4, 3), bar_color=YELLOW),
    ]
    s5 = GanttStage("5", "Тестирование и документация")
    s5.tasks = [
        GanttTask("5.1", "Модульное и интеграционное тестирование", date(2026, 4, 1), date(2026, 4, 14), bar_color=BLUE),
        GanttTask("5.2", "Системное и приёмочное тестирование", date(2026, 4, 4), date(2026, 4, 10), bar_color=BLUE),
        GanttTask("5.3", "Оформление ВКР (разделы 1–3)", date(2026, 4, 11), date(2026, 5, 1), bar_color=YELLOW),
    ]
    return [s1, s2, s3, s4, s5]


def _stage_to_group_task(stage: GanttStage) -> GanttTask:
    """Сформировать строку-«группу» из этапа: даты охватывают все подзадачи."""
    start = min(t.start for t in stage.tasks)
    end = max(t.end for t in stage.tasks)
    return GanttTask(stage.wbs, stage.name, start, end, is_group=True)


def render(out: Path) -> None:
    """Сгенерировать табличную диаграмму Ганта проекта."""
    img, draw = new_canvas(CANVAS, WHITE)
    title_fnt = font(28, bold=True)
    hdr_fnt = font(16, bold=True)
    cell_fnt = font(14)
    section_fnt = font(15, bold=True)
    foot_fnt = font(13)

    table_cols = (
        ("№\nИСР", 70),
        ("Название задачи", 580),
        ("Дата\nначала", 130),
        ("Дата\nокончания", 130),
        ("Прод.\nдней", 90),
        ("%", 60),
    )
    table_w = sum(w for _, w in table_cols)
    table_x = 30
    chart_x = table_x + table_w + 8
    chart_w = CANVAS[0] - chart_x - 30

    top_y = 60
    header_h = 56

    draw.text((table_x, 14), "Диаграмма Ганта — проект «Система интеллектуального анализа цен»", font=title_fnt, fill=INK)

    cx = table_x
    for label, w in table_cols:
        rect = (cx, top_y, cx + w, top_y + header_h)
        draw.rectangle(rect, fill=BLUE_DARK_HDR, outline=LINE, width=1)
        lines = label.split("\n")
        lh = hdr_fnt.size + 2
        ty = top_y + (header_h - len(lines) * lh) // 2
        for ln in lines:
            tw = text_width(draw, ln, hdr_fnt)
            draw.text((cx + (w - tw) // 2, ty), ln, font=hdr_fnt, fill=WHITE)
            ty += lh
        cx += w

    week_w = chart_w / TOTAL_WEEKS
    band_top = top_y
    band_h = header_h
    draw.rectangle((chart_x, band_top, chart_x + chart_w, band_top + band_h // 2), fill=BLUE_DARK_HDR, outline=LINE, width=1)
    stage_label = "ЭТАП 1"
    sl_w = text_width(draw, stage_label, hdr_fnt)
    draw.text((chart_x + (chart_w - sl_w) // 2, band_top + band_h // 4 - hdr_fnt.size // 2), stage_label, font=hdr_fnt, fill=WHITE)

    week_hdr_y = band_top + band_h // 2
    for w_i in range(TOTAL_WEEKS):
        x1 = chart_x + int(w_i * week_w)
        x2 = chart_x + int((w_i + 1) * week_w)
        draw.rectangle((x1, week_hdr_y, x2, week_hdr_y + band_h // 2), fill=BLUE_DARK_HDR, outline=LINE, width=1)
        label = f"Неделя {w_i + 1}"
        lw = text_width(draw, label, cell_fnt)
        draw.text((x1 + (x2 - x1 - lw) // 2, week_hdr_y + (band_h // 2 - cell_fnt.size) // 2), label, font=cell_fnt, fill=WHITE)

    row_h = 38
    y = top_y + header_h
    row_idx = 0

    for stage in stages():
        grp = _stage_to_group_task(stage)
        _draw_section_row(draw, table_x, y, table_cols, grp, hdr_fnt, section_fnt)
        _draw_section_chart(draw, chart_x, y, week_w, grp, row_h)
        y += row_h
        for task in stage.tasks:
            row_idx += 1
            bg = ROW_ALT if row_idx % 2 == 0 else WHITE
            _draw_task_row(draw, table_x, y, table_cols, task, cell_fnt, bg)
            _draw_task_chart(draw, chart_x, y, week_w, task, row_h, bg)
            y += row_h

    draw.text((table_x, y + 16), "Две рамки Ганта: разработка системы интеллектуального анализа цен | ВКР 2026", font=foot_fnt, fill=MUTED)
    save_png(img, out)


def _draw_section_row(
    draw,
    x: int,
    y: int,
    table_cols: tuple[tuple[str, int], ...],
    grp: GanttTask,
    hdr_fnt,
    section_fnt,
) -> None:
    """Нарисовать сплошную плашку группы (этап разработки) в таблице."""
    total = sum(w for _, w in table_cols)
    rect = (x, y, x + total, y + 38)
    draw.rectangle(rect, fill=BLUE_LIGHT, outline=LINE, width=1)
    cx = x
    for _, w in table_cols:
        cx += w
        draw.line([(cx, y), (cx, y + 38)], fill=LINE, width=1)
    cx = x
    wbs_w = table_cols[0][1]
    draw.text((cx + (wbs_w - text_width(draw, grp.wbs, hdr_fnt)) // 2, y + (38 - hdr_fnt.size) // 2), grp.wbs, font=hdr_fnt, fill=INK)
    draw.text((cx + wbs_w + 10, y + (38 - section_fnt.size) // 2), grp.name, font=section_fnt, fill=INK)


def _draw_section_chart(draw, chart_x: int, y: int, week_w: float, grp: GanttTask, row_h: int) -> None:
    """Нарисовать строку группы в области графика (тонкая подложка)."""
    chart_total = int(week_w * TOTAL_WEEKS)
    draw.rectangle((chart_x, y, chart_x + chart_total, y + row_h), fill=BLUE_LIGHT, outline=LINE, width=1)


def _draw_task_row(
    draw,
    x: int,
    y: int,
    table_cols: tuple[tuple[str, int], ...],
    task: GanttTask,
    cell_fnt,
    bg: str,
) -> None:
    """Нарисовать строку подзадачи в таблице."""
    total = sum(w for _, w in table_cols)
    draw.rectangle((x, y, x + total, y + 38), fill=bg, outline=LINE, width=1)
    cx = x
    duration = _duration_days(task.start, task.end)
    values = [
        task.wbs,
        task.name,
        task.start.strftime("%d.%m.%y"),
        task.end.strftime("%d.%m.%y"),
        str(duration),
        f"{task.progress}%",
    ]
    aligns = ["center", "left", "center", "center", "center", "center"]
    for (val, (label, w), align) in zip(values, table_cols, aligns, strict=True):
        if align == "left":
            draw.text((cx + 10, y + (38 - cell_fnt.size) // 2), val, font=cell_fnt, fill=INK)
        else:
            tw = text_width(draw, val, cell_fnt)
            draw.text((cx + (w - tw) // 2, y + (38 - cell_fnt.size) // 2), val, font=cell_fnt, fill=INK)
        cx += w
        draw.line([(cx, y), (cx, y + 38)], fill=LINE, width=1)


def _draw_task_chart(draw, chart_x: int, y: int, week_w: float, task: GanttTask, row_h: int, bg: str) -> None:
    """Нарисовать полосу выполнения задачи в области графика."""
    chart_total = int(week_w * TOTAL_WEEKS)
    draw.rectangle((chart_x, y, chart_x + chart_total, y + row_h), fill=bg, outline=LINE, width=1)
    day_w = (week_w * TOTAL_WEEKS) / ((PROJECT_END - PROJECT_START).days + 1)
    sx = chart_x + int((task.start - PROJECT_START).days * day_w)
    ex = chart_x + int((task.end - PROJECT_START).days * day_w + day_w)
    bar_top = y + 8
    bar_bottom = y + row_h - 8
    draw.rectangle((sx, bar_top, ex, bar_bottom), fill=task.bar_color, outline=GREEN_DARK if task.bar_color == YELLOW else INK, width=1)


def main() -> int:
    """Сгенерировать табличную диаграмму Ганта."""
    render(OUT / "gantt_table_style.png")
    print(f"Gantt сгенерирована: {OUT / 'gantt_table_style.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
