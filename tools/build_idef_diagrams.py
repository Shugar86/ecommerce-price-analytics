#!/usr/bin/env python3
"""Генератор диаграмм IDEF0 / IDEF3 (Pillow).

Производит файлы в ``assets/diagrams/``:

* ``idef0_asis.png``  — модель A-0 «As-Is» (ручной мониторинг цен);
* ``idef0_tobe.png``  — модель A-0 «To-Be» (автоматизированная система);
* ``idef0_a1_etl.png`` — декомпозиция А1 (ETL-контур);
* ``idef0_a2_matching.png`` — декомпозиция А2 (интеллектуальное сопоставление);
* ``idef3_anomaly_detection.png`` — IDEF3 процесс обнаружения аномалий.

Стиль блока (см. ``docs/idef0.png``, ``docs/idef.png``, ``docs/idef555.png``):

* белый фон, тонкий чёрный контур;
* левый-нижний угол — ``0?``, правый-нижний — № блока;
* в нижней части блока — штриховка (зона механизмов);
* входы — слева, выходы — справа, управление — сверху, механизмы — снизу;
* подписи стрелок мелким шрифтом без подложки.

IDEF3-соединения выполнены через круг с буквой ``O`` (OR-junction)
и пометкой ``J1``, ``J2`` — см. ``docs/idef3333.png``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageDraw, ImageFont

from _diagram_common import (
    DARK,
    HATCH,
    INK,
    WHITE,
    arrowhead,
    draw_centered_text,
    draw_left_text,
    font,
    hatched_band,
    new_canvas,
    save_png,
    text_width,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagrams"

CANVAS = (2400, 1500)  # used only by decomposition diagrams (A1, A2, IDEF3)


@dataclass(frozen=True)
class IdefBlock:
    """Функциональный блок IDEF0 / IDEF3.

    Attributes:
        number: Номер блока (правый-нижний угол).
        label: Имя функции.
        x: Левая граница.
        y: Верхняя граница.
        w: Ширина блока.
        h: Высота блока.
    """

    number: str
    label: str
    x: int
    y: int
    w: int = 280
    h: int = 180


def draw_block(draw: ImageDraw.ImageDraw, b: IdefBlock, fnt: ImageFont.FreeTypeFont, small: ImageFont.FreeTypeFont) -> None:
    """Нарисовать IDEF-блок (рамка + штриховая зона механизмов + номер)."""
    rect = (b.x, b.y, b.x + b.w, b.y + b.h)
    draw.rectangle(rect, fill=WHITE, outline=DARK, width=2)
    draw_centered_text(draw, (b.x + 16, b.y + 10, b.x + b.w - 16, b.y + b.h - 38), b.label, fnt, INK)
    hatched_band(draw, (b.x + 6, b.y + b.h - 28, b.x + b.w - 6, b.y + b.h - 12), spacing=6, color=HATCH, width=1)
    draw.text((b.x + 8, b.y + b.h - 22), "0?", font=small, fill=INK)
    num_w = text_width(draw, b.number, small)
    draw.text((b.x + b.w - num_w - 8, b.y + b.h - 22), b.number, font=small, fill=INK)


def label_pin(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    *,
    color: str = INK,
    align: str = "left",
) -> None:
    """Подписать стрелку рядом с её началом или концом."""
    x, y = pos
    lines = text.split("\n")
    lh = fnt.size + 4
    if align == "left":
        for i, ln in enumerate(lines):
            draw.text((x, y + i * lh), ln, font=fnt, fill=color)
    elif align == "right":
        for i, ln in enumerate(lines):
            w = text_width(draw, ln, fnt)
            draw.text((x - w, y + i * lh), ln, font=fnt, fill=color)
    else:
        for i, ln in enumerate(lines):
            w = text_width(draw, ln, fnt)
            draw.text((x - w // 2, y + i * lh), ln, font=fnt, fill=color)


def input_arrow(draw: ImageDraw.ImageDraw, block: IdefBlock, y_offset: int, label: str, fnt: ImageFont.FreeTypeFont, *, start_x: int = 130) -> None:
    """Нарисовать вход (стрелка ← в левый бок блока) с подписью слева."""
    y = block.y + y_offset
    end = (block.x, y)
    draw.line([(start_x, y), end], fill=INK, width=2)
    arrowhead(draw, end, "right", color=INK)
    label_pin(draw, (start_x, y - (label.count("\n") + 1) * (fnt.size + 4) - 6), label, fnt)


def output_arrow(draw: ImageDraw.ImageDraw, block: IdefBlock, y_offset: int, label: str, fnt: ImageFont.FreeTypeFont, *, end_x: int = 1900) -> None:
    """Нарисовать выход (стрелка → из правого бока блока)."""
    y = block.y + y_offset
    start = (block.x + block.w, y)
    end = (end_x, y)
    draw.line([start, end], fill=INK, width=2)
    arrowhead(draw, end, "right", color=INK)
    label_pin(draw, (end_x + 12, y - (label.count("\n") + 1) * (fnt.size + 4) // 2 - 2), label, fnt, align="left")


def control_arrow(draw: ImageDraw.ImageDraw, block: IdefBlock, x_offset: int, label: str, fnt: ImageFont.FreeTypeFont, *, top_y: int = 130, color: str = INK) -> None:
    """Нарисовать стрелку управления (сверху вниз в блок)."""
    x = block.x + x_offset
    end = (x, block.y)
    draw.line([(x, top_y), end], fill=color, width=2)
    arrowhead(draw, end, "down", color=color)
    label_pin(draw, (x + 8, top_y - 6), label, fnt, color=color)


def mechanism_arrow(draw: ImageDraw.ImageDraw, block: IdefBlock, x_offset: int, label: str, fnt: ImageFont.FreeTypeFont, *, bottom_y: int = 1380) -> None:
    """Нарисовать стрелку механизма (снизу вверх в блок)."""
    x = block.x + x_offset
    end = (x, block.y + block.h)
    draw.line([(x, bottom_y), end], fill=INK, width=2)
    arrowhead(draw, end, "up", color=INK)
    label_pin(draw, (x + 8, bottom_y + 4), label, fnt)


def _idef0_a0(
    out: Path,
    *,
    title: str,
    block_label: str,
    inputs: list[str],
    controls: list[str],
    mechanisms: list[str],
    outputs: list[str],
    label_num: str = "A0",
    canvas: tuple[int, int] = (1750, 1100),
    block_x: int = 560,
    block_y: int = 310,
    block_w: int = 630,
    block_h: int = 420,
    in_start_x: int = 140,
    out_end_x: int = 1545,
    ctl_top_y: int = 175,
    mech_bot_y: int = 870,
) -> None:
    """Рендер компактной формы A-0 IDEF0 (один центральный блок).

    Args:
        out: Путь к итоговому PNG.
        title: Заголовок диаграммы.
        block_label: Текст внутри центрального блока.
        inputs: Подписи входных стрелок (слева).
        controls: Подписи стрелок управления (сверху).
        mechanisms: Подписи стрелок механизмов (снизу).
        outputs: Подписи выходных стрелок (справа).
        label_num: Номер блока (правый-нижний угол).
        canvas: Размер холста (ширина, высота).
        block_x: Левая граница центрального блока.
        block_y: Верхняя граница центрального блока.
        block_w: Ширина блока.
        block_h: Высота блока.
        in_start_x: X-начало входных стрелок.
        out_end_x: X-конец выходных стрелок.
        ctl_top_y: Y-начало стрелок управления.
        mech_bot_y: Y-начало стрелок механизмов (снизу вверх).
    """
    img, draw = new_canvas(canvas, WHITE)
    title_fnt = font(28, bold=True)
    fnt = font(17)
    small = font(13, bold=True)
    arrow_fnt = font(14)

    cw = canvas[0]
    draw.text((cw // 2 - text_width(draw, title, title_fnt) // 2, 40), title, font=title_fnt, fill=INK)

    block = IdefBlock(label_num, block_label, block_x, block_y, w=block_w, h=block_h)
    draw_block(draw, block, fnt, small)

    in_step = block.h // (len(inputs) + 1)
    for i, lbl in enumerate(inputs, 1):
        input_arrow(draw, block, in_step * i, lbl, arrow_fnt, start_x=in_start_x)

    out_step = block.h // (len(outputs) + 1)
    for i, lbl in enumerate(outputs, 1):
        output_arrow(draw, block, out_step * i, lbl, arrow_fnt, end_x=out_end_x)

    c_step = block.w // (len(controls) + 1)
    for i, lbl in enumerate(controls, 1):
        control_arrow(draw, block, c_step * i, lbl, arrow_fnt, top_y=ctl_top_y)

    m_step = block.w // (len(mechanisms) + 1)
    for i, lbl in enumerate(mechanisms, 1):
        mechanism_arrow(draw, block, m_step * i, lbl, arrow_fnt, bottom_y=mech_bot_y)

    draw.rectangle((25, 25, canvas[0] - 25, canvas[1] - 25), outline=MUTED_FRAME, width=1)
    save_png(img, out)


MUTED_FRAME = "#C8C8C8"


def render_idef0_asis(out: Path) -> None:
    """Сгенерировать диаграмму IDEF0 A-0 «As-Is» (ручной процесс)."""
    _idef0_a0(
        out,
        title="IDEF0 / A-0 «Мониторинг рыночных цен» — модель As-Is",
        block_label="Мониторинг и анализ\nрыночных цен\n(ручной процесс)",
        inputs=[
            "Прайс-листы\nпоставщиков\n(YML, XLS, CSV)",
            "Сайты\nконкурентов",
            "Внутренние данные\nкомпании",
        ],
        controls=[
            "Ценовая политика\nорганизации",
            "Регламент частоты\nмониторинга",
            "Товарный\nклассификатор",
        ],
        mechanisms=[
            "Аналитик",
            "Microsoft Excel",
            "Корпоративная\nпочта",
        ],
        outputs=[
            "Обновлённый прайс-лист\nорганизации",
            "Аналитический отчёт\nдля руководства",
            "Решения\nо ценообразовании",
        ],
        canvas=(1700, 1060),
        block_x=540, block_y=295, block_w=620, block_h=410,
        in_start_x=130, out_end_x=1510,
        ctl_top_y=165, mech_bot_y=840,
    )


def render_idef0_tobe(out: Path) -> None:
    """Сгенерировать диаграмму IDEF0 A-0 «To-Be» (автоматизированная система)."""
    _idef0_a0(
        out,
        title="IDEF0 / A-0 «Автоматизированный анализ цен» — модель To-Be",
        block_label="Автоматизированный мониторинг\nи интеллектуальный анализ цен\n(микросервисная система)",
        inputs=[
            "URL-адреса\nисточников данных",
            "Курсы валют\n(ЦБ РФ)",
            "Внутренние данные\nорганизации",
        ],
        controls=[
            "Ценовая\nполитика",
            "Конфигурация\nрасписания ETL",
            "Пороги уверенности\nсопоставлений",
            "Параметры\nдетекции аномалий",
        ],
        mechanisms=[
            "Collector\n(ETL)",
            "AI Worker\n(ML)",
            "Web API\n(FastAPI)",
            "Telegram Bot\n(Aiogram 3)",
            "PostgreSQL 15\n(СУБД)",
        ],
        outputs=[
            "Аналитические дашборды\n(real-time)",
            "Ценовые решения\nаналитика",
            "Уведомления об аномалиях\n(Telegram)",
        ],
        canvas=(1900, 1150),
        block_x=590, block_y=310, block_w=700, block_h=460,
        in_start_x=140, out_end_x=1660,
        ctl_top_y=175, mech_bot_y=920,
    )


def render_idef0_a1_etl(out: Path) -> None:
    """Сгенерировать декомпозицию А1 — ETL-контур."""
    img, draw = new_canvas(CANVAS, WHITE)
    title_fnt = font(34, bold=True)
    fnt = font(18)
    small = font(14, bold=True)
    arrow_fnt = font(15)

    title = "Декомпозиция A1: Автоматизированный ETL-контур"
    draw.text((CANVAS[0] // 2 - text_width(draw, title, title_fnt) // 2, 50), title, font=title_fnt, fill=INK)

    blocks = (
        IdefBlock("1", "Загрузка данных\nпо расписанию", 210, 540, w=380, h=290),
        IdefBlock("2", "Потоковый\nсинтаксический\nанализ", 700, 540, w=380, h=290),
        IdefBlock("3", "Лексическая\nнормализация\nнаименований", 1190, 540, w=380, h=290),
        IdefBlock("4", "Идемпотентное\nсохранение\n(UPSERT)", 1680, 540, w=380, h=290),
    )
    for b in blocks:
        draw_block(draw, b, fnt, small)

    inter_labels = ("HTTP-поток данных\nYML / XLS / CSV", "Распарсенные\nполя", "name_norm,\nprice_rub")
    for i, lbl in enumerate(inter_labels):
        a = blocks[i]
        b = blocks[i + 1]
        y = a.y + a.h // 2
        draw.line([(a.x + a.w, y), (b.x, y)], fill=INK, width=2)
        arrowhead(draw, (b.x, y), "right", color=INK)
        mid_x = a.x + a.w + 10
        draw_left_text(draw, (mid_x, y - 36), lbl, arrow_fnt, INK)

    controls = (
        ("Конфигурация\nрасписания", blocks[0], 0.5),
        ("Правила\nнормализации", blocks[1], 0.5),
        ("Схема БД\n(Alembic)", blocks[2], 0.5),
        ("ФЗ 152\n«О перс. данных»", blocks[3], 0.5),
    )
    for lbl, b, off in controls:
        x = int(b.x + b.w * off)
        draw.line([(x, 280), (x, b.y)], fill=INK, width=2)
        arrowhead(draw, (x, b.y), "down", color=INK)
        draw_left_text(draw, (x + 8, 220), lbl, arrow_fnt, INK)

    mechanisms = (
        ("aiohttp\nClientSession", blocks[0]),
        ("lxml.iterparse,\nopenpyxl, csv", blocks[1]),
        ("TextNormalizer\n(app/matching)", blocks[2]),
        ("SQLAlchemy 2.0\n(asyncpg)", blocks[3]),
    )
    for lbl, b in mechanisms:
        x = b.x + b.w // 2
        draw.line([(x, 1050), (x, b.y + b.h)], fill=INK, width=2)
        arrowhead(draw, (x, b.y + b.h), "up", color=INK)
        draw_left_text(draw, (x + 8, 1060), lbl, arrow_fnt, INK)

    inputs = (
        ("URL-адреса\nисточников", blocks[0].y + 90),
        ("Расписание\n(cron)", blocks[0].y + 200),
    )
    for lbl, y in inputs:
        draw.line([(110, y), (blocks[0].x, y)], fill=INK, width=2)
        arrowhead(draw, (blocks[0].x, y), "right", color=INK)
        draw_left_text(draw, (110, y - 50), lbl, arrow_fnt, INK)

    outputs = (
        ("Нормализованные\nпозиции (products)", blocks[3].y + 60),
        ("История цен\n(price_history)", blocks[3].y + 150),
        ("Состояние источника\n(source_health)", blocks[3].y + 240),
    )
    end_x = 2120
    for lbl, y in outputs:
        draw.line([(blocks[3].x + blocks[3].w, y), (end_x, y)], fill=INK, width=2)
        arrowhead(draw, (end_x, y), "right", color=INK)
        draw_left_text(draw, (end_x + 8, y - 24), lbl, arrow_fnt, INK)

    draw.rectangle((30, 30, CANVAS[0] - 30, CANVAS[1] - 30), outline=MUTED_FRAME, width=1)
    save_png(img, out)


def render_idef0_a2_matching(out: Path) -> None:
    """Сгенерировать декомпозицию А2 — интеллектуальное сопоставление."""
    img, draw = new_canvas(CANVAS, WHITE)
    title_fnt = font(34, bold=True)
    fnt = font(17)
    small = font(14, bold=True)
    arrow_fnt = font(15)

    title = "Декомпозиция A2: Интеллектуальное сопоставление номенклатуры"
    draw.text((CANVAS[0] // 2 - text_width(draw, title, title_fnt) // 2, 50), title, font=title_fnt, fill=INK)

    blocks = (
        IdefBlock("1", "Точное\nсопоставление\nbarcode /\nvendor_code", 210, 540, w=380, h=290),
        IdefBlock("2", "TF-IDF cosine\nsimilarity\n(scikit-learn)", 700, 540, w=380, h=290),
        IdefBlock("3", "Jaccard +\nчисловые\nпараметры", 1190, 540, w=380, h=290),
        IdefBlock("4", "Gemini-фильтр\n«серой зоны»\n0.15–0.70", 1680, 540, w=380, h=290),
    )
    for b in blocks:
        draw_block(draw, b, fnt, small)

    inter = ("Если нет\nточного ключа", "tfidf_score", "«серая зона»\n0.15–0.70")
    for i, lbl in enumerate(inter):
        a = blocks[i]
        b = blocks[i + 1]
        y = a.y + a.h // 2
        draw.line([(a.x + a.w, y), (b.x, y)], fill=INK, width=2)
        arrowhead(draw, (b.x, y), "right", color=INK)
        mid_x = a.x + a.w + 10
        draw_left_text(draw, (mid_x, y - 40), lbl, arrow_fnt, INK)

    controls = (
        ("Порог точного\nсовпадения", blocks[0]),
        ("Веса\nTF-IDF", blocks[1]),
        ("Пороги\n0.15 / 0.70", blocks[2]),
        ("API-ключ\nGemini", blocks[3]),
    )
    for lbl, b in controls:
        x = b.x + b.w // 2
        draw.line([(x, 280), (x, b.y)], fill=INK, width=2)
        arrowhead(draw, (x, b.y), "down", color=INK)
        draw_left_text(draw, (x + 8, 220), lbl, arrow_fnt, INK)

    mechanisms = (
        ("SQL\nlookup", blocks[0]),
        ("TfidfVectorizer\n(биграммы)", blocks[1]),
        ("set ops +\nregex", blocks[2]),
        ("Gemini 1.5\nFlash API", blocks[3]),
    )
    for lbl, b in mechanisms:
        x = b.x + b.w // 2
        draw.line([(x, 1050), (x, b.y + b.h)], fill=INK, width=2)
        arrowhead(draw, (x, b.y + b.h), "up", color=INK)
        draw_left_text(draw, (x + 8, 1060), lbl, arrow_fnt, INK)

    inputs = (
        ("name_norm A,\nname_norm B", blocks[0].y + 70),
        ("barcode A,\nbarcode B", blocks[0].y + 160),
        ("vendor_code A,\nvendor_code B", blocks[0].y + 240),
    )
    for lbl, y in inputs:
        draw.line([(110, y), (blocks[0].x, y)], fill=INK, width=2)
        arrowhead(draw, (blocks[0].x, y), "right", color=INK)
        draw_left_text(draw, (110, y - 40), lbl, arrow_fnt, INK)

    outputs = (
        ("CONFIRMED\n(score ≥ 0.70)", blocks[3].y + 50),
        ("GEMINI_VALIDATED\n(conf ≥ 0.80)", blocks[3].y + 130),
        ("REJECTED\n(score < 0.15)", blocks[3].y + 200),
        ("PENDING\n(ручная проверка)", blocks[3].y + 270),
    )
    end_x = 2120
    for lbl, y in outputs:
        draw.line([(blocks[3].x + blocks[3].w, y), (end_x, y)], fill=INK, width=2)
        arrowhead(draw, (end_x, y), "right", color=INK)
        draw_left_text(draw, (end_x + 8, y - 20), lbl, arrow_fnt, INK)

    draw.rectangle((30, 30, CANVAS[0] - 30, CANVAS[1] - 30), outline=MUTED_FRAME, width=1)
    save_png(img, out)


def or_junction(draw: ImageDraw.ImageDraw, center: tuple[int, int], name: str, fnt: ImageFont.FreeTypeFont, *, radius: int = 26) -> None:
    """Нарисовать OR-junction (круг с буквой O и меткой J1/J2 справа)."""
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=WHITE, outline=INK, width=2)
    fnt_o = font(28, bold=True)
    o_w = text_width(draw, "O", fnt_o)
    draw.text((cx - o_w // 2, cy - radius + 4), "O", font=fnt_o, fill=INK)
    j_w = text_width(draw, name, fnt)
    label_pad = 4
    label_x = cx + radius + 6
    label_y = cy - fnt.size // 2 - 2
    draw.rectangle(
        (label_x - 2, label_y - 1, label_x + j_w + label_pad, label_y + fnt.size + 4),
        fill=WHITE,
    )
    draw.text((label_x, label_y), name, font=fnt, fill=INK)


def render_idef3_anomaly(out: Path) -> None:
    """Сгенерировать IDEF3-диаграмму процесса обнаружения ценовых аномалий."""
    img, draw = new_canvas(CANVAS, WHITE)
    title_fnt = font(34, bold=True)
    fnt = font(18)
    small = font(14, bold=True)
    arrow_fnt = font(15)

    title = "Диаграмма IDEF3: Процесс обнаружения ценовых аномалий"
    draw.text((CANVAS[0] // 2 - text_width(draw, title, title_fnt) // 2, 50), title, font=title_fnt, fill=INK)

    source = IdefBlock("", "История цен\n(price_history)", 110, 260, w=240, h=130)
    rect = (source.x, source.y, source.x + source.w, source.y + source.h)
    draw.rectangle(rect, fill=WHITE, outline=DARK, width=2)
    draw_centered_text(draw, rect, source.label, fnt, INK)

    blocks_top = (
        IdefBlock("1", "Получение\nценового ряда\n(90 дней)", 460, 260, w=280, h=180),
        IdefBlock("2", "Расчёт SMA_w(t)\nи σ_w(t)", 840, 260, w=280, h=180),
        IdefBlock("3", "Проверка\n|P_t − SMA| > k·σ", 1220, 260, w=280, h=180),
        IdefBlock("4", "Классификация\nтипа аномалии", 1600, 260, w=280, h=180),
    )
    for b in blocks_top:
        draw_block(draw, b, fnt, small)

    branches = (
        IdefBlock("4a", "spike\n(резкий скачок)", 460, 720, w=320, h=180),
        IdefBlock("4b", "fake_discount\n(ложная скидка)", 870, 720, w=320, h=180),
        IdefBlock("4c", "zscore_return\n(статистическое\nотклонение)", 1280, 720, w=320, h=180),
    )
    for b in branches:
        draw_block(draw, b, fnt, small)

    sink = IdefBlock("5", "Запись результата\nв price_anomalies", 1760, 1080, w=460, h=180)
    draw_block(draw, sink, fnt, small)

    in_y = source.y + source.h // 2
    draw.line([(source.x + source.w, in_y), (blocks_top[0].x, in_y)], fill=INK, width=2)
    arrowhead(draw, (blocks_top[0].x, in_y), "right", color=INK)
    draw_left_text(draw, (source.x + source.w + 20, in_y - 28), "price series", arrow_fnt, INK)

    for i in range(len(blocks_top) - 1):
        a = blocks_top[i]
        b = blocks_top[i + 1]
        y = a.y + a.h // 2
        draw.line([(a.x + a.w, y), (b.x, y)], fill=INK, width=2)
        arrowhead(draw, (b.x, y), "right", color=INK)
        mid = (a.x + a.w + b.x) // 2
        labels = ("series", "SMA, σ", "anomaly flag")
        draw_left_text(draw, (mid - 35, y - 28), labels[i], arrow_fnt, INK)

    jx, jy = blocks_top[3].x + blocks_top[3].w // 2, 580
    block4 = blocks_top[3]
    draw.line([(block4.x + block4.w // 2, block4.y + block4.h), (jx, jy - 26)], fill=INK, width=2)
    arrowhead(draw, (jx, jy - 26), "down", color=INK)
    draw_left_text(draw, (jx + 36, (block4.y + block4.h + jy - 26) // 2 - 12), "классификация", arrow_fnt, INK)

    for b in branches:
        tx = b.x + b.w // 2
        ty = b.y
        draw.line([(jx, jy + 26), (jx, jy + 100), (tx, jy + 100), (tx, ty)], fill=INK, width=2)
        arrowhead(draw, (tx, ty), "down", color=INK)

    j2x, j2y = 1130, 1020
    for b in branches:
        bx = b.x + b.w // 2
        by = b.y + b.h
        draw.line([(bx, by), (bx, j2y), (j2x if bx > j2x else j2x - 26, j2y)], fill=INK, width=2)
        target_x = j2x - 26 if bx < j2x else j2x + 26
        arrowhead(draw, (target_x, j2y), "right" if bx < j2x else "left", color=INK)

    draw.line([(j2x + 26, j2y), (sink.x + 30, j2y), (sink.x + 30, sink.y)], fill=INK, width=2)
    arrowhead(draw, (sink.x + 30, sink.y), "down", color=INK)
    draw_left_text(draw, (j2x + 40, j2y - 28), "INSERT", arrow_fnt, INK)

    # Junctions рисуем последними, чтобы их подписи (J1, J2) не перекрывались стрелками.
    or_junction(draw, (jx, jy), "J1", arrow_fnt)
    or_junction(draw, (j2x, j2y), "J2", arrow_fnt)

    draw.rectangle((30, 30, CANVAS[0] - 30, CANVAS[1] - 30), outline=MUTED_FRAME, width=1)
    save_png(img, out)


def main() -> int:
    """Сгенерировать все IDEF-диаграммы."""
    render_idef0_asis(OUT / "idef0_asis.png")
    render_idef0_tobe(OUT / "idef0_tobe.png")
    render_idef0_a1_etl(OUT / "idef0_a1_etl.png")
    render_idef0_a2_matching(OUT / "idef0_a2_matching.png")
    render_idef3_anomaly(OUT / "idef3_anomaly_detection.png")
    print(f"IDEF-диаграммы сгенерированы: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
