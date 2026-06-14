"""Общие утилиты рендера диаграмм (Pillow).

Содержит шрифты, базовые операции рисования, штриховку IDEF0/DFD
и обёртку переноса текста — используется генераторами
``build_dfd_diagrams.py``, ``build_idef_diagrams.py``, ``build_gantt.py``,
``build_kanban.py``.

Стиль диаграмм соответствует образцам ``docs/dfd.png``, ``docs/idef.png``,
``docs/gant.png``, ``docs/kanban.png``: белый фон, тонкие чёрные линии,
жёлтые хранилища данных, штриховка зоны механизмов.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont


FONT_DIR: Final[Path] = Path("/usr/share/fonts/truetype/dejavu")

# Palette — нейтральная пастельная гамма, общая для всех диаграмм.
WHITE: Final[str] = "#FFFFFF"
INK: Final[str] = "#1A1A1A"
DARK: Final[str] = "#2A2A2A"
LINE: Final[str] = "#555555"
MUTED: Final[str] = "#9AA0A6"
YELLOW: Final[str] = "#F5D447"
YELLOW_SOFT: Final[str] = "#FFE9A8"
BLUE: Final[str] = "#2C5F8A"
BLUE_LIGHT: Final[str] = "#D6E5F1"
BLUE_DARK_HDR: Final[str] = "#1F4A6E"
ROW_ALT: Final[str] = "#EAF2FA"
GREEN: Final[str] = "#5BA672"
GREEN_DARK: Final[str] = "#3B7B4F"
RED_ACCENT: Final[str] = "#C8474E"
LAVENDER: Final[str] = "#D8D0E8"
HATCH: Final[str] = "#333333"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загрузить DejaVu Sans указанного кегля.

    Args:
        size: Высота шрифта в пикселях.
        bold: True для bold-начертания.

    Returns:
        Объект ImageFont, готовый к использованию в Pillow.
    """
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size=size)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> int:
    """Ширина текста в пикселях для текущего шрифта."""
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def text_height(fnt: ImageFont.FreeTypeFont) -> int:
    """Высота строки в пикселях (для line-spacing)."""
    return fnt.size + 4


def wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.FreeTypeFont) -> list[str]:
    """Перенести текст по ширине ``max_width``.

    Args:
        draw: Объект ImageDraw, нужен для измерения текста.
        text: Исходный текст; \\n воспринимается как принудительный перевод.
        max_width: Максимальная ширина строки в пикселях.
        fnt: Шрифт для измерения.

    Returns:
        Список строк, каждая из которых помещается в ``max_width``.
    """
    out: list[str] = []
    for line in text.split("\n"):
        words = line.split()
        if not words:
            out.append("")
            continue
        cur = ""
        for word in words:
            cand = f"{cur} {word}".strip()
            if text_width(draw, cand, fnt) <= max_width:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = word
        if cur:
            out.append(cur)
    return out or [""]


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    color: str = INK,
    *,
    padding: int = 8,
) -> None:
    """Нарисовать центрированный многострочный текст в прямоугольнике."""
    x1, y1, x2, y2 = rect
    lines = wrap(draw, text, x2 - x1 - padding * 2, fnt)
    lh = text_height(fnt)
    total = len(lines) * lh
    y = y1 + ((y2 - y1) - total) // 2
    for line in lines:
        w = text_width(draw, line, fnt)
        x = x1 + ((x2 - x1) - w) // 2
        draw.text((x, y), line, font=fnt, fill=color)
        y += lh


def draw_left_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    color: str = INK,
    *,
    max_width: int | None = None,
) -> None:
    """Нарисовать левый текст начиная с ``pos`` (опционально с переносом)."""
    x, y = pos
    lh = text_height(fnt)
    if max_width is None:
        for line in text.split("\n"):
            draw.text((x, y), line, font=fnt, fill=color)
            y += lh
        return
    for line in wrap(draw, text, max_width, fnt):
        draw.text((x, y), line, font=fnt, fill=color)
        y += lh


def hatched_band(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    *,
    spacing: int = 6,
    color: str = HATCH,
    width: int = 1,
) -> None:
    """Заполнить прямоугольник диагональной штриховкой (IDEF0-зона механизмов).

    Args:
        draw: Объект Pillow для отрисовки.
        rect: (x1, y1, x2, y2) — заполняемая область.
        spacing: Шаг между диагоналями, px.
        color: Цвет линий штриховки.
        width: Толщина каждой линии.
    """
    x1, y1, x2, y2 = rect
    w = x2 - x1
    h = y2 - y1
    img_band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img_band)
    for offset in range(-h, w, spacing):
        d.line([(offset, 0), (offset + h, h)], fill=color, width=width)
    parent = draw._image  # type: ignore[attr-defined]
    parent.paste(img_band, (x1, y1), img_band)


def arrowhead(
    draw: ImageDraw.ImageDraw,
    tip: tuple[int, int],
    direction: str,
    *,
    size: int = 14,
    color: str = INK,
) -> None:
    """Нарисовать стрелку-«галочку» в направлении ``direction``.

    Args:
        draw: Объект Pillow.
        tip: Координата острия стрелки.
        direction: 'right' | 'left' | 'up' | 'down'.
        size: Длина усов стрелки в пикселях.
        color: Цвет заливки треугольника.
    """
    x, y = tip
    if direction == "right":
        pts = [(x, y), (x - size, y - size // 2), (x - size, y + size // 2)]
    elif direction == "left":
        pts = [(x, y), (x + size, y - size // 2), (x + size, y + size // 2)]
    elif direction == "down":
        pts = [(x, y), (x - size // 2, y - size), (x + size // 2, y - size)]
    else:
        pts = [(x, y), (x - size // 2, y + size), (x + size // 2, y + size)]
    draw.polygon(pts, fill=color)


def line_with_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    direction: str | None = None,
    color: str = INK,
    width: int = 2,
) -> None:
    """Нарисовать ортогональную линию со стрелкой на конце."""
    draw.line([start, end], fill=color, width=width)
    if direction is None:
        if end[0] > start[0]:
            direction = "right"
        elif end[0] < start[0]:
            direction = "left"
        elif end[1] > start[1]:
            direction = "down"
        else:
            direction = "up"
    arrowhead(draw, end, direction, color=color)


def new_canvas(size: tuple[int, int], background: str = WHITE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Создать новый холст с заданным фоном."""
    img = Image.new("RGB", size, background)
    drw = ImageDraw.Draw(img)
    return img, drw


def save_png(img: Image.Image, path: Path) -> None:
    """Сохранить PNG с DPI 300 и mkdir -p родительского каталога."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, dpi=(300, 300), optimize=True)
