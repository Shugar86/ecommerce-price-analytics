#!/usr/bin/env python3
"""Генератор канбан-доски проекта (Pillow).

Производит ``assets/diagrams/kanban_board.png`` в стиле образца
``docs/kanban.png``: четыре колонки, заголовки серым шрифтом,
карточки — белый прямоугольник с тонкой каймой и зелёной иконкой
часов слева от даты.

Содержание карточек взято из колонок ВКР §3.4.1 и задач из
``gantt_project_timeline.mmd``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageDraw, ImageFont

from _diagram_common import (
    GREEN,
    GREEN_DARK,
    INK,
    LINE,
    MUTED,
    WHITE,
    font,
    new_canvas,
    save_png,
    text_height,
    wrap,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagrams"

CANVAS = (2400, 1500)
COL_BG = "#EFF1F4"
HDR_FG = "#384047"


@dataclass
class KanbanCard:
    """Карточка канбан-доски.

    Attributes:
        title: Заголовок задачи.
        when: Дата или диапазон дат (отображается рядом с иконкой часов).
    """

    title: str
    when: str


@dataclass
class KanbanColumn:
    """Колонка канбан-доски.

    Attributes:
        title: Заголовок колонки.
        cards: Список карточек, отображаемых в колонке.
    """

    title: str
    cards: list[KanbanCard] = field(default_factory=list)


def _clock_icon(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int = 11, color: str = GREEN, color_dark: str = GREEN_DARK) -> None:
    """Нарисовать стилизованную иконку часов (зелёный круг + стрелки)."""
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline=color_dark, width=1)
    draw.line([(cx, cy), (cx, cy - radius + 3)], fill=WHITE, width=2)
    draw.line([(cx, cy), (cx + radius - 5, cy)], fill=WHITE, width=2)


def _draw_card(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, card: KanbanCard, title_fnt: ImageFont.FreeTypeFont, when_fnt: ImageFont.FreeTypeFont) -> int:
    """Нарисовать одну карточку и вернуть её высоту."""
    pad = 14
    title_lines = wrap(draw, card.title, w - 2 * pad, title_fnt)
    title_h = len(title_lines) * text_height(title_fnt)
    when_h = text_height(when_fnt)
    card_h = pad + title_h + 8 + when_h + pad

    rect = (x, y, x + w, y + card_h)
    draw.rectangle(rect, fill=WHITE, outline=LINE, width=1)

    ty = y + pad
    for line in title_lines:
        draw.text((x + pad, ty), line, font=title_fnt, fill=INK)
        ty += text_height(title_fnt)

    icon_cx = x + pad + 11
    icon_cy = ty + 8 + when_fnt.size // 2
    _clock_icon(draw, (icon_cx, icon_cy))
    draw.text((icon_cx + 18, ty + 8), card.when, font=when_fnt, fill="#445566")

    return card_h


def _draw_column(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    column: KanbanColumn,
    hdr_fnt: ImageFont.FreeTypeFont,
    title_fnt: ImageFont.FreeTypeFont,
    when_fnt: ImageFont.FreeTypeFont,
) -> None:
    """Нарисовать одну колонку: фон, заголовок, карточки."""
    rect = (x, y, x + w, y + h)
    draw.rectangle(rect, fill=COL_BG, outline=LINE, width=1)
    draw.text((x + 18, y + 16), column.title, font=hdr_fnt, fill=HDR_FG)
    draw.text((x + w - 80, y + 16), "+ + ⋯", font=when_fnt, fill=MUTED)
    draw.line([(x + 16, y + 56), (x + w - 16, y + 56)], fill=LINE, width=1)

    cy = y + 72
    card_x = x + 16
    card_w = w - 32
    gap = 12
    for card in column.cards:
        ch = _draw_card(draw, card_x, cy, card_w, card, title_fnt, when_fnt)
        cy += ch + gap
        if cy > y + h - 60:
            break
    draw.text((card_x + 8, cy + 6), "+ Добавить карточку", font=when_fnt, fill=MUTED)


def board() -> list[KanbanColumn]:
    """Сформировать содержание канбан-доски.

    Содержание основано на ВКР §3.4.1 (четыре колонки: «Очередь / В работе /
    Проверка / Готово») и наборе задач разработки прототипа.
    """
    queue = KanbanColumn(
        "Очередь",
        [
            KanbanCard("Архивирование устаревшей истории цен", "к 15.05.26"),
            KanbanCard("Добавление нового источника (Etmonline)", "следующая итерация"),
            KanbanCard("Расширение метрик /ru-benchmark", "не приоритет"),
            KanbanCard("UI: фильтр по бренду в /alerts", "к 30.05.26"),
        ],
    )
    in_work = KanbanColumn(
        "В работе",
        [
            KanbanCard("Оформление ВКР (разделы 1–3)", "11.04.26 — 01.05.26"),
            KanbanCard("Системное и приёмочное тестирование", "04.04.26 — 10.04.26"),
        ],
    )
    review = KanbanColumn(
        "Проверка",
        [
            KanbanCard("Модульное и интеграционное тестирование", "01.04.26 — 14.04.26"),
            KanbanCard("Эталонный набор данных RuEcom-2026", "25.03.26 — 03.04.26"),
            KanbanCard("Интеграция Gemini 2.5 Flash", "22.03.26 — 26.03.26"),
        ],
    )
    done = KanbanColumn(
        "Готово",
        [
            KanbanCard("Анализ предметной области и постановка задачи", "02.02.26 — 11.02.26"),
            KanbanCard("Проектирование архитектуры и модели данных", "12.02.26 — 19.02.26"),
            KanbanCard("Разработка комплекта UML-диаграмм", "09.02.26 — 15.02.26"),
            KanbanCard("Схема БД и миграции Alembic", "20.02.26 — 23.02.26"),
            KanbanCard("ETL-конвейер YML / XLS / CSV", "24.02.26 — 07.03.26"),
            KanbanCard("Лексическая нормализация наименований", "08.03.26 — 13.03.26"),
            KanbanCard("REST API и веб-интерфейс (FastAPI + Jinja2)", "10.03.26 — 23.03.26"),
            KanbanCard("Telegram-бот (Aiogram 3)", "24.03.26 — 29.03.26"),
            KanbanCard("Детектор аномалий (Z-score, fake discount)", "08.03.26 — 13.03.26"),
            KanbanCard("TF-IDF / Jaccard сопоставление (AI Worker)", "14.03.26 — 21.03.26"),
        ],
    )
    return [queue, in_work, review, done]


def render(out: Path) -> None:
    """Сгенерировать канбан-доску проекта."""
    img, draw = new_canvas(CANVAS, "#F8F9FB")
    title_fnt = font(28, bold=True)
    hdr_fnt = font(20, bold=True)
    card_fnt = font(16, bold=True)
    when_fnt = font(13)

    draw.text((30, 14), "Канбан-доска проекта «Система интеллектуального анализа цен»", font=title_fnt, fill=INK)

    columns = board()
    margin = 30
    top_y = 70
    bottom_y = CANVAS[1] - 30
    available_w = CANVAS[0] - 2 * margin
    col_gap = 16
    col_w = (available_w - col_gap * (len(columns) - 1)) // len(columns)

    for idx, column in enumerate(columns):
        x = margin + idx * (col_w + col_gap)
        _draw_column(draw, x, top_y, col_w, bottom_y - top_y, column, hdr_fnt, card_fnt, when_fnt)

    save_png(img, out)


def main() -> int:
    """Сгенерировать канбан-доску в ``assets/diagrams/kanban_board.png``."""
    render(OUT / "kanban_board.png")
    print(f"Kanban сгенерирована: {OUT / 'kanban_board.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
