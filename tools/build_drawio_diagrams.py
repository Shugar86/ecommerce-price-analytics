#!/usr/bin/env python3
"""Generate polished draw.io sources and high-resolution PNG UML diagrams.

The repository keeps the final image filenames stable (`assets/uml/*.png`) so
the thesis Markdown does not need link churn, while editable `.drawio` sources
are stored separately in `assets/diagrams/drawio/`.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
UML_DIR = ROOT / "assets" / "uml"
DRAWIO_DIR = ROOT / "assets" / "diagrams" / "drawio"

CANVAS = (2400, 1500)
BG = "#F8FAFC"
INK = "#111827"
MUTED = "#475569"
BLUE = "#2563EB"
BLUE_LIGHT = "#DBEAFE"
GREEN = "#059669"
GREEN_LIGHT = "#D1FAE5"
ORANGE = "#EA580C"
ORANGE_LIGHT = "#FFEDD5"
VIOLET = "#7C3AED"
VIOLET_LIGHT = "#EDE9FE"
GRAY = "#CBD5E1"
WHITE = "#FFFFFF"


@dataclass(frozen=True)
class Box:
    """Drawable node used both for PNG rendering and draw.io XML generation."""

    ident: str
    label: str
    x: int
    y: int
    w: int
    h: int
    fill: str = WHITE
    stroke: str = BLUE


@dataclass(frozen=True)
class Edge:
    """Connection between two diagram nodes."""

    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class Diagram:
    """Diagram definition for rendering and draw.io source generation."""

    name: str
    title: str
    boxes: tuple[Box, ...]
    edges: tuple[Edge, ...]


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a Unicode-capable font."""
    base = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
    path = f"{base}-Bold.ttf" if bold else f"{base}.ttf"
    return ImageFont.truetype(path, size=size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.FreeTypeFont) -> list[str]:
    """Wrap text to fit inside a node."""
    lines: list[str] = []
    for raw_line in text.split("\n"):
        words = raw_line.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fnt: ImageFont.FreeTypeFont, fill: str) -> None:
    """Draw centered multiline text inside a rectangle."""
    x1, y1, x2, y2 = box
    lines = wrap_text(draw, text, x2 - x1 - 42, fnt)
    line_height = fnt.size + 8
    total_height = len(lines) * line_height
    y = y1 + (y2 - y1 - total_height) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        x = x1 + (x2 - x1 - (bbox[2] - bbox[0])) / 2
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = MUTED, width: int = 5) -> None:
    """Draw a line with an arrow head."""
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 22
    points = [
        end,
        (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6)),
        (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6)),
    ]
    draw.polygon(points, fill=color)


def box_center(box: Box) -> tuple[int, int]:
    """Return node center point."""
    return (box.x + box.w // 2, box.y + box.h // 2)


def side_points(source: Box, target: Box) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return visually pleasing side points for a directed edge."""
    sx, sy = box_center(source)
    tx, ty = box_center(target)
    if abs(tx - sx) >= abs(ty - sy):
        start = (source.x + (source.w if tx >= sx else 0), sy)
        end = (target.x if tx >= sx else target.x + target.w, ty)
    else:
        start = (sx, source.y + (source.h if ty >= sy else 0))
        end = (tx, target.y if ty >= sy else target.y + target.h)
    return start, end


def render_png(diagram: Diagram, output: Path) -> None:
    """Render a high-resolution PNG for a diagram."""
    img = Image.new("RGB", CANVAS, BG)
    draw = ImageDraw.Draw(img)
    title_font = font(50, bold=True)
    label_font = font(30, bold=True)
    small_font = font(24)

    draw.text((110, 70), diagram.title, font=title_font, fill=INK)
    draw.line([(110, 145), (2290, 145)], fill=GRAY, width=3)

    by_id = {box.ident: box for box in diagram.boxes}
    for edge in diagram.edges:
        source = by_id[edge.source]
        target = by_id[edge.target]
        start, end = side_points(source, target)
        draw_arrow(draw, start, end)
        if edge.label:
            mx = (start[0] + end[0]) // 2
            my = (start[1] + end[1]) // 2
            bbox = draw.textbbox((0, 0), edge.label, font=small_font)
            pad = 10
            draw.rounded_rectangle(
                (mx - (bbox[2] - bbox[0]) // 2 - pad, my - 22, mx + (bbox[2] - bbox[0]) // 2 + pad, my + 22),
                radius=12,
                fill=BG,
            )
            draw.text((mx - (bbox[2] - bbox[0]) // 2, my - 17), edge.label, font=small_font, fill=MUTED)

    for box in diagram.boxes:
        rect = (box.x, box.y, box.x + box.w, box.y + box.h)
        draw.rounded_rectangle(rect, radius=28, fill=box.fill, outline=box.stroke, width=5)
        draw.rectangle((box.x, box.y, box.x + box.w, box.y + 18), fill=box.stroke)
        center_text(draw, rect, box.label, label_font, INK)

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, dpi=(300, 300), quality=95)


def render_svg(diagram: Diagram, output: Path) -> None:
    """Render a scalable SVG companion for a diagram."""
    by_id = {box.ident: box for box in diagram.boxes}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS[0]}" height="{CANVAS[1]}" viewBox="0 0 {CANVAS[0]} {CANVAS[1]}">',
        f'<rect width="100%" height="100%" fill="{BG}"/>',
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M2,2 L10,6 L2,10 Z" fill="#475569"/></marker></defs>',
        f'<text x="110" y="105" font-family="DejaVu Sans, Arial" font-size="50" font-weight="700" fill="{INK}">{escape(diagram.title)}</text>',
        f'<line x1="110" y1="145" x2="2290" y2="145" stroke="{GRAY}" stroke-width="3"/>',
    ]
    for edge in diagram.edges:
        start, end = side_points(by_id[edge.source], by_id[edge.target])
        parts.append(
            f'<line x1="{start[0]}" y1="{start[1]}" x2="{end[0]}" y2="{end[1]}" stroke="{MUTED}" stroke-width="5" marker-end="url(#arrow)"/>'
        )
        if edge.label:
            mx = (start[0] + end[0]) // 2
            my = (start[1] + end[1]) // 2
            parts.append(
                f'<text x="{mx}" y="{my - 10}" text-anchor="middle" font-family="DejaVu Sans, Arial" font-size="24" fill="{MUTED}">{escape(edge.label)}</text>'
            )
    for box in diagram.boxes:
        parts.append(
            f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="28" fill="{box.fill}" stroke="{box.stroke}" stroke-width="5"/>'
        )
        parts.append(f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="18" fill="{box.stroke}"/>')
        lines = box.label.split("\n")
        start_y = box.y + box.h / 2 - (len(lines) - 1) * 20
        for offset, line in enumerate(lines):
            parts.append(
                f'<text x="{box.x + box.w / 2}" y="{start_y + offset * 40:.0f}" text-anchor="middle" dominant-baseline="middle" font-family="DejaVu Sans, Arial" font-size="30" font-weight="700" fill="{INK}">{escape(line)}</text>'
            )
    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def drawio_xml(diagram: Diagram) -> str:
    """Create a minimal editable draw.io XML source for a diagram."""
    cells = [
        '<mxCell id="0"/>',
        '<mxCell id="1" parent="0"/>',
    ]
    for box in diagram.boxes:
        style = (
            "rounded=1;whiteSpace=wrap;html=1;fontSize=14;fontFamily=Times New Roman;"
            f"fillColor={box.fill};strokeColor={box.stroke};strokeWidth=2;"
        )
        cells.append(
            f'<mxCell id="{box.ident}" value="{escape(box.label)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{box.x / 2:.0f}" y="{box.y / 2:.0f}" width="{box.w / 2:.0f}" height="{box.h / 2:.0f}" as="geometry"/>'
            "</mxCell>"
        )
    for index, edge in enumerate(diagram.edges, start=1):
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;fontSize=12;fontFamily=Times New Roman;endArrow=block;"
        label = html.escape(edge.label)
        cells.append(
            f'<mxCell id="edge{index}" value="{label}" style="{style}" edge="1" parent="1" source="{edge.source}" target="{edge.target}">'
            '<mxGeometry relative="1" as="geometry"/>'
            "</mxCell>"
        )
    content = "".join(cells)
    return (
        '<mxfile host="app.diagrams.net" modified="2026-05-08T00:00:00.000Z" agent="Cursor" version="24.7.17">'
        f'<diagram name="{escape(diagram.title)}">'
        f'<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1200" pageHeight="750" math="0" shadow="0">'
        f"<root>{content}</root>"
        "</mxGraphModel>"
        "</diagram>"
        "</mxfile>"
    )


def write_drawio(diagram: Diagram, output: Path) -> None:
    """Write a draw.io source file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(drawio_xml(diagram), encoding="utf-8")


def diagrams() -> tuple[Diagram, ...]:
    """Return all diagrams used by the thesis."""
    return (
        Diagram(
            "deployment_diagram",
            "Диаграмма развёртывания системы",
            (
                Box("user", "Аналитик / администратор", 140, 640, 330, 140, GREEN_LIGHT, GREEN),
                Box("web", "Web API\nFastAPI + Jinja2", 720, 360, 360, 150, BLUE_LIGHT, BLUE),
                Box("bot", "Telegram Bot\nAiogram 3", 720, 770, 360, 150, BLUE_LIGHT, BLUE),
                Box("collector", "Collector\nETL: YML / XLS / CSV", 1280, 300, 390, 150, ORANGE_LIGHT, ORANGE),
                Box("worker", "AI Worker\nTF-IDF / аномалии / Gemini", 1280, 620, 390, 170, VIOLET_LIGHT, VIOLET),
                Box("db", "PostgreSQL 15\nистория цен и сопоставления", 1860, 470, 380, 170, WHITE, INK),
            ),
            (
                Edge("user", "web", "HTTP"),
                Edge("user", "bot", "Telegram"),
                Edge("web", "db", "SQL"),
                Edge("bot", "db", "SQL"),
                Edge("collector", "db", "UPSERT"),
                Edge("worker", "db", "batch jobs"),
            ),
        ),
        Diagram(
            "use_case_user",
            "Диаграмма вариантов использования: аналитик",
            (
                Box("actor", "Аналитик", 160, 640, 260, 130, GREEN_LIGHT, GREEN),
                Box("dash", "Просмотр аналитической панели", 760, 240, 420, 120, BLUE_LIGHT, BLUE),
                Box("market", "Мониторинг рынка и индекса цены", 760, 450, 420, 120, BLUE_LIGHT, BLUE),
                Box("matches", "Проверка кандидатов сопоставления", 760, 660, 420, 120, BLUE_LIGHT, BLUE),
                Box("alerts", "Анализ аномалий и уведомлений", 760, 870, 420, 120, BLUE_LIGHT, BLUE),
                Box("export", "Экспорт отчётов", 1420, 555, 360, 120, ORANGE_LIGHT, ORANGE),
                Box("llm", "Получение пояснений LLM", 1420, 765, 360, 120, VIOLET_LIGHT, VIOLET),
            ),
            (
                Edge("actor", "dash"),
                Edge("actor", "market"),
                Edge("actor", "matches"),
                Edge("actor", "alerts"),
                Edge("dash", "export"),
                Edge("matches", "llm"),
            ),
        ),
        Diagram(
            "use_case_admin",
            "Диаграмма вариантов использования: администратор",
            (
                Box("actor", "Администратор", 170, 640, 300, 130, GREEN_LIGHT, GREEN),
                Box("deploy", "Запуск контейнеров", 760, 270, 400, 120, BLUE_LIGHT, BLUE),
                Box("logs", "Контроль журналов", 760, 480, 400, 120, BLUE_LIGHT, BLUE),
                Box("sources", "Проверка состояния источников", 760, 690, 400, 120, BLUE_LIGHT, BLUE),
                Box("backup", "Резервное копирование БД", 760, 900, 400, 120, BLUE_LIGHT, BLUE),
                Box("env", "Настройка переменных окружения", 1390, 585, 430, 130, ORANGE_LIGHT, ORANGE),
            ),
            (
                Edge("actor", "deploy"),
                Edge("actor", "logs"),
                Edge("actor", "sources"),
                Edge("actor", "backup"),
                Edge("deploy", "env"),
                Edge("sources", "env"),
            ),
        ),
        Diagram(
            "sequence_diagram",
            "Диаграмма последовательности обработки запроса",
            (
                Box("browser", "Пользователь", 160, 250, 270, 110, GREEN_LIGHT, GREEN),
                Box("web", "Web API", 610, 250, 270, 110, BLUE_LIGHT, BLUE),
                Box("service", "Сервис аналитики", 1060, 250, 330, 110, ORANGE_LIGHT, ORANGE),
                Box("db", "PostgreSQL", 1570, 250, 300, 110, WHITE, INK),
                Box("chart", "HTML + Chart.js", 1960, 250, 300, 110, VIOLET_LIGHT, VIOLET),
                Box("history", "История цен", 1180, 710, 380, 130, BLUE_LIGHT, BLUE),
            ),
            (
                Edge("browser", "web", "GET /product"),
                Edge("web", "service", "prepare view model"),
                Edge("service", "db", "SELECT"),
                Edge("db", "service", "rows"),
                Edge("service", "history", "aggregate"),
                Edge("service", "chart", "dataset"),
                Edge("chart", "browser", "response"),
            ),
        ),
        Diagram(
            "activity_diagram",
            "Диаграмма деятельности процесса сбора данных",
            (
                Box("start", "Старт цикла", 140, 650, 260, 120, GREEN_LIGHT, GREEN),
                Box("rates", "Получение курсов валют", 560, 360, 360, 120, BLUE_LIGHT, BLUE),
                Box("source", "Выбор источника", 560, 700, 360, 120, BLUE_LIGHT, BLUE),
                Box("load", "Загрузка файла/API", 1060, 360, 360, 120, ORANGE_LIGHT, ORANGE),
                Box("parse", "Парсинг и нормализация", 1060, 700, 360, 120, ORANGE_LIGHT, ORANGE),
                Box("save", "UPSERT в PostgreSQL", 1550, 525, 360, 120, VIOLET_LIGHT, VIOLET),
                Box("log", "Журнал результата", 1990, 525, 300, 120, WHITE, INK),
            ),
            (
                Edge("start", "rates"),
                Edge("start", "source"),
                Edge("rates", "load"),
                Edge("source", "load"),
                Edge("load", "parse"),
                Edge("parse", "save"),
                Edge("save", "log"),
            ),
        ),
        Diagram(
            "class_diagram",
            "Диаграмма классов предметной модели",
            (
                Box("product", "Product\nid, name, brand\nname_norm", 170, 300, 390, 180, BLUE_LIGHT, BLUE),
                Box("history", "PriceHistory\nproduct_id, price\ncollected_at", 760, 300, 390, 180, GREEN_LIGHT, GREEN),
                Box("match", "ProductMatch\nscore, status\nllm_verdict", 1350, 300, 390, 180, ORANGE_LIGHT, ORANGE),
                Box("anomaly", "PriceAnomaly\ntype, severity\nexplanation", 760, 720, 390, 180, VIOLET_LIGHT, VIOLET),
                Box("collector", "Collector\nparse(), normalize()\nsave()", 170, 720, 390, 180, WHITE, INK),
                Box("validator", "GeminiValidator\nvalidate_pair()\nexplain()", 1350, 720, 390, 180, WHITE, INK),
            ),
            (
                Edge("collector", "product", "creates"),
                Edge("product", "history", "1:N"),
                Edge("product", "match", "N:M"),
                Edge("history", "anomaly", "detects"),
                Edge("validator", "match", "validates"),
            ),
        ),
        Diagram(
            "er_diagram",
            "Логическая модель данных",
            (
                Box("products", "products\nPK id\nname, brand, source", 160, 320, 390, 170, BLUE_LIGHT, BLUE),
                Box("price_history", "price_history\nPK id\nFK product_id\nprice, collected_at", 760, 250, 410, 190, GREEN_LIGHT, GREEN),
                Box("matches", "product_matches\nFK product_a_id\nFK product_b_id\nscore, status", 1360, 320, 430, 190, ORANGE_LIGHT, ORANGE),
                Box("anomalies", "price_anomalies\nFK product_id\ntype, severity", 760, 760, 410, 170, VIOLET_LIGHT, VIOLET),
                Box("rates", "exchange_rates\ncurrency, rate, date", 1360, 760, 430, 150, WHITE, INK),
            ),
            (
                Edge("products", "price_history", "1:N"),
                Edge("products", "matches", "N:M"),
                Edge("products", "anomalies", "1:N"),
                Edge("rates", "price_history", "normalizes"),
            ),
        ),
        Diagram(
            "llm_flow",
            "Схема интеграции языковой модели",
            (
                Box("pair", "Пара товаров\nиз серой зоны", 150, 620, 360, 150, BLUE_LIGHT, BLUE),
                Box("rules", "Локальные эвристики\nTF-IDF, Jaccard, параметры", 700, 370, 430, 160, GREEN_LIGHT, GREEN),
                Box("prompt", "Промпт с доменом\nи JSON-форматом", 700, 790, 430, 160, ORANGE_LIGHT, ORANGE),
                Box("gemini", "Gemini 1.5 Flash\nвалидация", 1300, 580, 390, 160, VIOLET_LIGHT, VIOLET),
                Box("db", "База данных\nverdict + confidence", 1860, 580, 390, 160, WHITE, INK),
            ),
            (
                Edge("pair", "rules", "fast path"),
                Edge("rules", "prompt", "uncertain"),
                Edge("prompt", "gemini", "request"),
                Edge("gemini", "db", "JSON verdict"),
                Edge("rules", "db", "local result"),
            ),
        ),
    )


def main() -> int:
    """Generate all draw.io sources and PNG exports."""
    UML_DIR.mkdir(parents=True, exist_ok=True)
    DRAWIO_DIR.mkdir(parents=True, exist_ok=True)
    for diagram in diagrams():
        write_drawio(diagram, DRAWIO_DIR / f"{diagram.name}.drawio")
        render_png(diagram, UML_DIR / f"{diagram.name}.png")
        render_svg(diagram, UML_DIR / f"{diagram.name}.svg")
    # Backward-compatible combined use-case filename.
    user_png = UML_DIR / "use_case_user.png"
    if user_png.exists():
        (UML_DIR / "use_case_diagram.png").write_bytes(user_png.read_bytes())
        (UML_DIR / "use_case_diagram.svg").write_text(
            (UML_DIR / "use_case_user.svg").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (DRAWIO_DIR / "use_case_diagram.drawio").write_text(
            (DRAWIO_DIR / "use_case_user.drawio").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    print(f"Созданы draw.io исходники: {DRAWIO_DIR}")
    print(f"Обновлены PNG-диаграммы: {UML_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
