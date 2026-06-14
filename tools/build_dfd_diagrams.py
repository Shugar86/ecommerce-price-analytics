#!/usr/bin/env python3
"""Генератор DFD-диаграмм в нотации Гейна–Сарсона (Pillow).

Производит ``assets/diagrams/dfd_level0.png`` (контекстная диаграмма)
и ``assets/diagrams/dfd_level1.png`` (декомпозиция системы).

Стиль соответствует образцу ``docs/dfd.png`` / ``docs/dfd666.png``:

* белый фон;
* внешняя сущность — прямоугольник с маркером ``1`` в левом-верхнем углу;
* процесс — прямоугольник с маркером ``0?`` слева-внизу, № справа-внизу
  и тонкой штрих-полосой под названием;
* хранилище данных — жёлтая горизонтальная плашка с № и именем таблицы;
* стрелки тонкие, подписи мелким шрифтом, ключевые потоки выделяются
  цветом (синий, красный) — по аналогии с ``dfd666.png``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageDraw, ImageFont

from _diagram_common import (
    BLUE,
    DARK,
    HATCH,
    INK,
    LINE,
    RED_ACCENT,
    WHITE,
    YELLOW,
    arrowhead,
    draw_centered_text,
    font,
    hatched_band,
    new_canvas,
    save_png,
    text_width,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagrams"

CANVAS = (2400, 1500)


@dataclass(frozen=True)
class ExternalEntity:
    """Внешняя сущность DFD: прямоугольник с маркером в углу.

    Attributes:
        number: Номер сущности (отображается в верхнем-левом углу).
        label: Имя сущности (центрируется внутри прямоугольника).
        x: Левая граница в пикселях.
        y: Верхняя граница в пикселях.
        w: Ширина в пикселях.
        h: Высота в пикселях.
    """

    number: int
    label: str
    x: int
    y: int
    w: int = 240
    h: int = 110


@dataclass(frozen=True)
class Process:
    """Процесс DFD в нотации Гейна–Сарсона.

    Attributes:
        number: Номер процесса (правый-верхний угол).
        marker: Текст в левом-верхнем углу, обычно ``0?``.
        label: Название процесса в центре.
        x: Левая граница.
        y: Верхняя граница.
        w: Ширина.
        h: Высота.
    """

    number: int
    marker: str
    label: str
    x: int
    y: int
    w: int = 360
    h: int = 150


@dataclass(frozen=True)
class DataStore:
    """Хранилище данных — жёлтая горизонтальная плашка.

    Attributes:
        number: Номер хранилища (отображается слева в плашке).
        label: Имя таблицы или сущности данных.
        x: Левая граница.
        y: Верхняя граница.
        w: Ширина.
        h: Высота.
    """

    number: int
    label: str
    x: int
    y: int
    w: int = 360
    h: int = 60


def draw_external(draw: ImageDraw.ImageDraw, e: ExternalEntity, fnt: ImageFont.FreeTypeFont, num_fnt: ImageFont.FreeTypeFont) -> None:
    """Нарисовать внешнюю сущность."""
    rect = (e.x, e.y, e.x + e.w, e.y + e.h)
    draw.rectangle(rect, fill=WHITE, outline=DARK, width=2)
    draw.rectangle((e.x, e.y, e.x + 32, e.y + 24), fill=WHITE, outline=DARK, width=2)
    draw.text((e.x + 10, e.y + 4), str(e.number), font=num_fnt, fill=INK)
    draw_centered_text(draw, (e.x + 36, e.y, e.x + e.w, e.y + e.h), e.label, fnt, INK)


def draw_process(draw: ImageDraw.ImageDraw, p: Process, fnt: ImageFont.FreeTypeFont, small_fnt: ImageFont.FreeTypeFont) -> None:
    """Нарисовать процесс DFD."""
    rect = (p.x, p.y, p.x + p.w, p.y + p.h)
    draw.rectangle(rect, fill=WHITE, outline=DARK, width=2)
    draw.text((p.x + 10, p.y + 8), p.marker, font=small_fnt, fill=INK)
    num_text = str(p.number)
    w = text_width(draw, num_text, small_fnt)
    draw.text((p.x + p.w - w - 10, p.y + 8), num_text, font=small_fnt, fill=INK)
    inner = (p.x + 20, p.y + 32, p.x + p.w - 20, p.y + p.h - 22)
    draw_centered_text(draw, inner, p.label, fnt, INK)
    hatched_band(draw, (p.x + 10, p.y + p.h - 14, p.x + p.w - 10, p.y + p.h - 6), spacing=5, color=HATCH, width=1)


def draw_store(draw: ImageDraw.ImageDraw, s: DataStore, fnt: ImageFont.FreeTypeFont, num_fnt: ImageFont.FreeTypeFont) -> None:
    """Нарисовать хранилище данных (жёлтая плашка с тенью)."""
    shadow = (s.x + 6, s.y + 6, s.x + s.w + 6, s.y + s.h + 6)
    draw.rectangle(shadow, fill="#C0C0C0")
    rect = (s.x, s.y, s.x + s.w, s.y + s.h)
    draw.rectangle(rect, fill=YELLOW, outline=DARK, width=2)
    draw.line([(s.x + 50, s.y), (s.x + 50, s.y + s.h)], fill=DARK, width=2)
    draw.text((s.x + 16, s.y + (s.h - num_fnt.size) // 2 - 2), str(s.number), font=num_fnt, fill=INK)
    draw_centered_text(draw, (s.x + 50, s.y, s.x + s.w, s.y + s.h), s.label, fnt, INK)


def arrow_label(draw: ImageDraw.ImageDraw, mid: tuple[int, int], text: str, fnt: ImageFont.FreeTypeFont, color: str = INK) -> None:
    """Подписать стрелку рядом с серединой потока (с белой подложкой)."""
    if not text:
        return
    lines = text.split("\n")
    w = max(text_width(draw, ln, fnt) for ln in lines) + 12
    h = len(lines) * (fnt.size + 4) + 4
    rect = (mid[0] - w // 2, mid[1] - h // 2, mid[0] + w // 2, mid[1] + h // 2)
    draw.rectangle(rect, fill=WHITE)
    y = rect[1] + 2
    for ln in lines:
        x = mid[0] - text_width(draw, ln, fnt) // 2
        draw.text((x, y), ln, font=fnt, fill=color)
        y += fnt.size + 4


def _flow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    color: str = INK,
    width: int = 3,
    label: str = "",
    label_at: int = 0,
    fnt: ImageFont.FreeTypeFont | None = None,
) -> None:
    """Нарисовать ломаную стрелку через указанные точки."""
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=width)
    last_a, last_b = points[-2], points[-1]
    if last_b[0] > last_a[0]:
        direction = "right"
    elif last_b[0] < last_a[0]:
        direction = "left"
    elif last_b[1] > last_a[1]:
        direction = "down"
    else:
        direction = "up"
    arrowhead(draw, last_b, direction, color=color)
    if label and fnt is not None:
        a, b = points[label_at], points[label_at + 1]
        mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        arrow_label(draw, mid, label, fnt, color=color)


def _draw_context_entity(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    label: str,
    fnt: ImageFont.FreeTypeFont,
) -> None:
    """Нарисовать внешнюю сущность контекстной DFD (прямоугольник с тонкой рамкой)."""
    draw.rectangle(rect, fill=WHITE, outline=DARK, width=2)
    draw_centered_text(draw, rect, label, fnt, INK)


def _draw_context_process(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    label: str,
    fnt: ImageFont.FreeTypeFont,
    num_fnt: ImageFont.FreeTypeFont,
) -> None:
    """Нарисовать центральный процесс (скруглённый прямоугольник с номером 0)."""
    x1, y1, x2, y2 = rect
    radius = 32
    draw.rounded_rectangle(rect, radius=radius, fill=WHITE, outline=DARK, width=3)
    draw.text((x1 + 20, y1 + 14), "0", font=num_fnt, fill=INK)
    draw_centered_text(draw, (x1 + 30, y1 + 30, x2 - 30, y2 - 20), label, fnt, INK)


def _elbow_arrow(
    draw: ImageDraw.ImageDraw,
    *,
    ex: int,
    ey: int,
    px: int,
    py: int,
    bend_x: int,
    off: int,
    color: str,
    label: str,
    fnt: ImageFont.FreeTypeFont,
    to_process: bool,
) -> None:
    """Нарисовать одну L-образную стрелку с подписью.

    Маршрут: горизонтально от сущности до ``bend_x``, затем вертикально
    до ``py``, затем горизонтально до процесса. ``off`` — вертикальный
    сдвиг (±) для разводки двух стрелок одного ребра.

    Args:
        ex: x-координата стартовой точки на ребре сущности.
        ey: y-центр сущности.
        px: x-координата точки входа/выхода на ребре процесса.
        py: y-координата точки входа/выхода на ребре процесса.
        bend_x: x-координата вертикального сегмента (перегиб).
        off: вертикальный сдвиг для разводки двух параллельных стрелок.
        color: цвет линии и наконечника.
        label: подпись потока (ставится у горизонтального сегмента со стороны сущности).
        fnt: шрифт подписи.
        to_process: направление — True если стрелка идёт к процессу.
    """
    ey_off = ey + off
    py_off = py + off
    pts = [(ex, ey_off), (bend_x, ey_off), (bend_x, py_off), (px, py_off)]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=2)
    tip = pts[-1]
    tip_dir = "right" if px > bend_x else "left"
    if to_process:
        arrowhead(draw, tip, tip_dir, color=color)
    else:
        arrowhead(draw, (ex, ey_off), "right" if ex > bend_x else "left", color=color)
    # label on the horizontal segment nearest the entity
    mid_x = (ex + bend_x) // 2
    arrow_label(draw, (mid_x, ey_off), label, fnt, color=color)


def render_level0(out: Path) -> None:
    """Сгенерировать DFD уровень 0 — контекстную диаграмму (компактный вариант).

    Чистая нотация Гейна–Сарсона: единственный процесс, шесть внешних
    сущностей, L-образные двунаправленные стрелки.
    """
    canvas = (1700, 1060)
    img, draw = new_canvas(canvas, WHITE)
    title_fnt = font(26, bold=True)
    sub_fnt = font(16)
    fnt = font(18)
    small_fnt = font(14)
    num_fnt = font(20, bold=True)

    draw.text((80, 32), "Контекстная диаграмма (DFD уровень 0)", font=title_fnt, fill=INK)
    draw.text((80, 78), "Система интеллектуального анализа цен | нотация Гейна–Сарсона", font=sub_fnt, fill=LINE)

    # ── Процессный блок ──────────────────────────────────────────────────────
    cx, cy = canvas[0] // 2, 520
    proc_w, proc_h = 420, 210
    proc_rect = (cx - proc_w // 2, cy - proc_h // 2, cx + proc_w // 2, cy + proc_h // 2)
    px_left  = proc_rect[0]   # 640
    px_right = proc_rect[2]   # 1060

    _draw_context_process(draw, proc_rect, "Система интеллектуального\nанализа цен", fnt, num_fnt)

    # ── Порты подключения на ребре процесса (25 / 50 / 75 %) ────────────────
    q1 = proc_rect[1] + proc_h // 4
    q2 = cy
    q3 = proc_rect[1] + 3 * proc_h // 4

    # ── Внешние сущности ────────────────────────────────────────────────────
    ent_w, ent_h = 210, 90
    left_x, right_x = 60, 1430
    left_ys  = [195, 395, 640]
    right_ys = [195, 395, 640]
    left_labels  = ["Поставщики\n(EKF, TDM, CARRETA)", "ЦБ РФ\n(курсы валют)", "Администратор"]
    right_labels = ["Аналитик", "Telegram Bot API", "Google Gemini API"]

    left_rects:  list[tuple[int, int, int, int]] = []
    right_rects: list[tuple[int, int, int, int]] = []
    for lbl, y in zip(left_labels, left_ys):
        r = (left_x, y, left_x + ent_w, y + ent_h)
        left_rects.append(r)
        _draw_context_entity(draw, r, lbl, fnt)
    for lbl, y in zip(right_labels, right_ys):
        r = (right_x, y, right_x + ent_w, y + ent_h)
        right_rects.append(r)
        _draw_context_entity(draw, r, lbl, fnt)

    bend_left  = (left_x + ent_w + px_left) // 2
    bend_right = (right_x + px_right) // 2

    left_flows = [
        (left_rects[0], q1, "YML / XLS / CSV", "лог сбора"),
        (left_rects[1], q2, "курсы валют",      "запрос периода"),
        (left_rects[2], q3, ".env / запуск",    "статус сервисов"),
    ]
    right_flows = [
        (right_rects[0], q1, "запросы аналитика", "HTML-дашборды"),
        (right_rects[1], q2, "запрос статуса",    "уведомления"),
        (right_rects[2], q3, "промпт name_norm",  "ответ Gemini"),
    ]

    OFF = 12
    for rect, conn_y, lbl_in, lbl_out in left_flows:
        _, ey1, ex2, ey2 = rect
        ey = (ey1 + ey2) // 2
        _elbow_arrow(draw, ex=ex2, ey=ey, px=px_left, py=conn_y,
                     bend_x=bend_left, off=+OFF, color=INK,  label=lbl_in,  fnt=small_fnt, to_process=True)
        _elbow_arrow(draw, ex=ex2, ey=ey, px=px_left, py=conn_y,
                     bend_x=bend_left, off=-OFF, color=LINE, label=lbl_out, fnt=small_fnt, to_process=False)

    for rect, conn_y, lbl_in, lbl_out in right_flows:
        ex1, ey1, _, ey2 = rect
        ey = (ey1 + ey2) // 2
        _elbow_arrow(draw, ex=ex1, ey=ey, px=px_right, py=conn_y,
                     bend_x=bend_right, off=+OFF, color=INK,  label=lbl_in,  fnt=small_fnt, to_process=True)
        _elbow_arrow(draw, ex=ex1, ey=ey, px=px_right, py=conn_y,
                     bend_x=bend_right, off=-OFF, color=LINE, label=lbl_out, fnt=small_fnt, to_process=False)

    # ── Легенда ───────────────────────────────────────────────────────────────
    legend_y = canvas[1] - 90
    draw.rectangle((80, legend_y, 130, legend_y + 32), outline=DARK, width=2, fill=WHITE)
    draw.text((142, legend_y + 7), "— внешняя сущность", font=small_fnt, fill=INK)
    draw.rounded_rectangle((450, legend_y, 500, legend_y + 32), radius=8, outline=DARK, width=2, fill=WHITE)
    draw.text((512, legend_y + 7), "— процесс", font=small_fnt, fill=INK)
    draw.line([(730, legend_y + 16), (800, legend_y + 16)], fill=INK, width=2)
    arrowhead(draw, (800, legend_y + 16), "right", color=INK)
    draw.text((812, legend_y + 7), "— поток к системе", font=small_fnt, fill=INK)
    draw.line([(1100, legend_y + 16), (1170, legend_y + 16)], fill=LINE, width=2)
    arrowhead(draw, (1100, legend_y + 16), "left", color=LINE)
    draw.text((1182, legend_y + 7), "— поток от системы", font=small_fnt, fill=LINE)

    save_png(img, out)


def render_level1(out: Path) -> None:
    """Сгенерировать DFD уровень 1 — декомпозицию системы (компактный вариант).

    Все потоки маршрутизируются L-образными ломаными с явными точками
    перегиба, которые обходят блоки процессов и хранилищ.
    """
    W, H = 2200, 1500
    img, draw = new_canvas((W, H), WHITE)
    title_fnt = font(28, bold=True)
    sub_fnt = font(17)
    fnt = font(15)
    small_fnt = font(12)
    num_fnt = font(12, bold=True)

    draw.text((80, 30), "DFD уровень 1 — Декомпозиция системы", font=title_fnt, fill=INK)
    draw.text((80, 78), "Система интеллектуального анализа цен | нотация Гейна–Сарсона", font=sub_fnt, fill=LINE)

    # ── Внешние сущности ────────────────────────────────────────────────────
    e1 = ExternalEntity(1, "Поставщики\n(EKF/TDM/CARRETA)", 55, 210, w=240, h=100)
    e2 = ExternalEntity(2, "ЦБ РФ",                         55, 400, w=240, h=85)
    e3 = ExternalEntity(3, "Администратор",                  55, 980, w=240, h=85)
    e4 = ExternalEntity(4, "Аналитик",                     1900, 210, w=240, h=85)
    e5 = ExternalEntity(5, "Gemini API",                   1900, 490, w=240, h=85)
    e6 = ExternalEntity(6, "Telegram\nBot API",            1900, 770, w=240, h=85)

    # ── Процессы ─────────────────────────────────────────────────────────────
    p1 = Process(1, "", "Сбор и парсинг\n(Collector)",            400, 210, w=265, h=105)
    p2 = Process(2, "", "Получение\nкурсов валют",                400, 400, w=265, h=105)
    p3 = Process(3, "", "Нормализация\nи сохранение\n(UPSERT)",   750, 200, w=265, h=125)
    p4 = Process(4, "", "Сопоставление\nноменклатуры\n(TF-IDF)",  1130, 200, w=265, h=125)
    p5 = Process(5, "", "Обнаружение\nаномалий\n(Z-score)",        750, 790, w=265, h=115)
    p6 = Process(6, "", "Веб-интерфейс\nи Telegram-бот",          1130, 790, w=265, h=115)

    # ── Хранилища данных ─────────────────────────────────────────────────────
    ds1 = DataStore(1, "products",        750, 510, w=265, h=50)
    ds2 = DataStore(2, "price_history",  1130, 510, w=265, h=50)
    ds3 = DataStore(3, "exchange_rates",  400, 610, w=265, h=50)

    for e in (e1, e2, e3, e4, e5, e6):
        draw_external(draw, e, fnt, num_fnt)
    for p in (p1, p2, p3, p4, p5, p6):
        draw_process(draw, p, fnt, small_fnt)
    for s in (ds1, ds2, ds3):
        draw_store(draw, s, fnt, num_fnt)

    # ── Вспомогательные функции ──────────────────────────────────────────────
    def _r(o: ExternalEntity | Process | DataStore) -> int:
        return o.x + o.w

    def _b(o: ExternalEntity | Process | DataStore) -> int:
        return o.y + o.h

    def _cx(o: ExternalEntity | Process | DataStore) -> int:
        return o.x + o.w // 2

    def _cy(o: ExternalEntity | Process | DataStore) -> int:
        return o.y + o.h // 2

    # Коридоры без блоков (новый холст 2200×1500):
    #   x=737  — зазор между DS3/P2 (right≤665) и P3/DS1 (left=750)
    #   x=1415 — правее DS2/P4 (right≤1395)
    #   x=1870 — правее процессов, левее E4/E5/E6 (left=1900)
    #   y=430  — между P3/P4 bottom (325) и DS1/DS2 top (510)
    #   y=680  — между DS1/DS2 bottom (560) и P5/P6 top (790)
    #   y=1030 — ниже P5/P6 bottom (905)

    flows: list[tuple[list[tuple[int, int]], str, str, int]] = [
        # 1. E1 → P1
        ([(_r(e1), _cy(e1)), (p1.x, _cy(e1))], "YML / XLS / CSV", INK, 0),
        # 2. E2 → P2
        ([(_r(e2), _cy(e2)), (p2.x, _cy(e2))], "XML курсы", INK, 0),
        # 3. P1 → P3
        ([(_r(p1), p1.y + 50), (p3.x, p3.y + 50)], "raw offer data", INK, 0),
        # 4. P2 → DS3: вертикаль вниз
        ([(_cx(p2), _b(p2)), (_cx(p2), ds3.y)], "rate", INK, 0),
        # 5. DS3 → P3: right → x=737 → up → P3 left
        ([(_r(ds3), _cy(ds3)), (737, _cy(ds3)), (737, _cy(p3)), (p3.x, _cy(p3))], "currency", INK, 0),
        # 6. P3 → P4
        ([(_r(p3), p3.y + 55), (p4.x, p4.y + 55)], "кандидаты", INK, 0),
        # 7. P3 → DS1: вертикаль вниз
        ([(_cx(p3), _b(p3)), (_cx(p3), ds1.y)], "UPSERT", BLUE, 0),
        # 8. P3 → DS2: down → y=430 → x=1090 → DS2 left
        ([(_r(p3) - 25, _b(p3)), (_r(p3) - 25, 430), (1090, 430), (1090, _cy(ds2)), (ds2.x, _cy(ds2))], "INSERT", BLUE, 2),
        # 9. DS2 → P5: down → y=680 → left → P5 top
        ([(_cx(ds2), _b(ds2)), (_cx(ds2), 680), (_cx(p5), 680), (_cx(p5), p5.y)], "series", INK, 1),
        # 10. P5 → P6
        ([(_r(p5), p5.y + 55), (p6.x, p6.y + 55)], "аномалии", INK, 0),
        # 11. P4 → P6: x=1415 правее DS2 (right=1395) → вниз → P6 top
        ([(_r(p4) + 20, _b(p4)), (_r(p4) + 20, 750), (_cx(p6), 750), (_cx(p6), p6.y)], "сопоставления", INK, 1),
        # 12. P4 → E5 (промпт)
        ([(_r(p4), p4.y + 35), (1870, p4.y + 35), (1870, e5.y + 35), (e5.x, e5.y + 35)], "промпт", INK, 1),
        # 13. E5 → P4 (вердикт)
        ([(e5.x, e5.y + 55), (1860, e5.y + 55), (1860, p4.y + 60), (_r(p4), p4.y + 60)], "вердикт", RED_ACCENT, 1),
        # 14. P6 → E4 (HTML+JSON)
        ([(_r(p6), p6.y + 22), (1870, p6.y + 22), (1870, e4.y + 28), (e4.x, e4.y + 28)], "HTML + JSON", INK, 1),
        # 15. E4 → P6 (запросы)
        ([(e4.x, e4.y + 52), (1860, e4.y + 52), (1860, p6.y + 50), (_r(p6), p6.y + 50)], "запросы", BLUE, 2),
        # 16. P6 → E6 (уведомления)
        ([(_r(p6), p6.y + 82), (1870, p6.y + 82), (1870, e6.y + 50), (e6.x, e6.y + 50)], "уведомления", INK, 1),
        # 17. E3 → P6: ниже P5 (y=1030) → x=1120 → P6 bottom left
        ([(_r(e3), _cy(e3)), (1120, _cy(e3)), (1120, _b(p6) - 18), (p6.x, _b(p6) - 18)], ".env / config", INK, 1),
    ]

    for pts, lbl, col, lat in flows:
        _flow(draw, pts, color=col, label=lbl, label_at=lat, fnt=small_fnt)

    save_png(img, out)


def main() -> int:
    """Сгенерировать оба DFD-PNG и вернуть код возврата процесса."""
    render_level0(OUT / "dfd_level0.png")
    render_level1(OUT / "dfd_level1.png")
    print(f"DFD сгенерированы: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
