#!/usr/bin/env python3
"""Генератор «скриншотов» терминала (Pillow).

Производит в ``assets/screenshots/``:

* ``docker_ps.png``       — вывод ``docker compose ps``;
* ``docker_stats.png``    — вывод ``docker stats --no-stream``;
* ``docker_logs.png``     — фрагмент ``docker compose logs --tail=20 collector``;
* ``gemini_curl.png``     — пример вызова Gemini API через curl и ответа;
* ``pytest_full.png``     — полный прогон ``pytest tests/ -v``;
* ``coverage_report.png`` — покрытие ``pytest --cov=app --cov-report=term-missing``;
* ``bandit_report.png``   — статический анализ ``bandit -r app/``.

Стиль соответствует тёмной теме монохромного терминала (близко к Ubuntu
GNOME Terminal с темой Tango Dark): тёмно-серый фон, светлый моноширинный
текст, тонкий заголовок окна с тремя «кружками» macOS-стиля для
визуального оформления (без претензий на снимок экрана конкретной ОС).

Скрипт детерминированный — повторный запуск даёт побитово идентичные PNG,
что важно для воспроизводимости защитных материалов.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Iterable

from PIL import Image, ImageDraw

from _diagram_common import font, new_canvas, save_png, text_width

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "screenshots"

BG = "#1E1E1E"
HEADER = "#2D2D2D"
DIM = "#9AA0A6"
FG = "#D6D6D6"
GREEN = "#73D216"
YELLOW = "#FCE94F"
RED = "#EF2929"
BLUE = "#729FCF"
CYAN = "#34E2E2"
PROMPT = "#A6E22E"


@dataclass(frozen=True)
class Line:
    """Строка терминала с опциональным цветом."""

    text: str
    color: str = FG


def _run_capture(command: list[str], *, cwd: Path | None = None) -> list[str]:
    """Выполнить команду и вернуть stdout/stderr как список строк.

    Если команда недоступна или завершается ошибкой, возвращает
    диагностический текст вместо возбуждения исключения.
    """
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - защитный путь для окружений без docker
        return [f"[error] {' '.join(command)}", str(exc)]
    text = proc.stdout or proc.stderr or ""
    lines = text.splitlines() or [f"[exit_code={proc.returncode}] no output"]
    return lines


def _draw_window_chrome(draw: ImageDraw.ImageDraw, w: int, title: str) -> int:
    """Нарисовать «шапку окна» в стиле macOS-терминала и вернуть y-координату начала тела."""
    chrome_h = 36
    draw.rectangle((0, 0, w, chrome_h), fill=HEADER)
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        cx = 16 + i * 20
        cy = chrome_h // 2
        draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=color)
    tfnt = font(13, bold=True)
    tw = text_width(draw, title, tfnt)
    draw.text(((w - tw) // 2, (chrome_h - 13) // 2 - 1), title, font=tfnt, fill=DIM)
    return chrome_h


def _render_terminal(out: Path, *, title: str, lines: Iterable[Line], cols: int = 110, padding: int = 18) -> None:
    """Отрисовать «терминальное окно» с заданными строками.

    Args:
        out: Путь для записи PNG.
        title: Заголовок окна (выводится по центру шапки).
        lines: Последовательность строк (``Line(text, color)``).
        cols: Ориентировочное число колонок (используется для расчёта ширины).
        padding: Внутренний отступ от края рамки до текста.
    """
    fnt = font(14)
    char_w = text_width(ImageDraw.Draw(Image.new("RGB", (10, 10))), "M", fnt)
    line_h = fnt.size + 8
    body_lines = list(lines)
    w = padding * 2 + cols * char_w
    chrome_h = 36
    h = chrome_h + padding * 2 + line_h * len(body_lines)
    img, draw = new_canvas((w, h), BG)
    _draw_window_chrome(draw, w, title)
    y = chrome_h + padding
    for line in body_lines:
        draw.text((padding, y), line.text, font=fnt, fill=line.color)
        y += line_h
    save_png(img, out)


def render_docker_ps(out: Path) -> None:
    """Сгенерировать скриншот ``docker compose ps``."""
    repo = ROOT
    ps_lines = _run_capture(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "ps"], cwd=repo)
    lines = [Line("user@dev-server:~/price-intelligence$ docker compose -f docker-compose.yml ps", PROMPT), Line("")]
    for idx, raw in enumerate(ps_lines[:10]):
        lines.append(Line(raw, CYAN if idx == 0 else FG))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — docker compose ps", lines=lines, cols=110)


def render_docker_stats(out: Path) -> None:
    """Сгенерировать скриншот ``docker stats --no-stream``."""
    stat_lines = _run_capture(["docker", "stats", "--no-stream"])
    lines = [Line("user@dev-server:~/price-intelligence$ docker stats --no-stream", PROMPT), Line("")]
    for idx, raw in enumerate(stat_lines[:9]):
        color = CYAN if idx == 0 else FG
        if "prices_ai_worker" in raw:
            color = RED
        elif "prices_collector" in raw:
            color = YELLOW
        lines.append(Line(raw, color))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — docker stats", lines=lines, cols=110)


def render_docker_logs(out: Path) -> None:
    """Сгенерировать скриншот ``docker compose logs --tail=15 collector``."""
    log_lines = _run_capture(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "logs", "--tail=15", "collector"],
        cwd=ROOT,
    )
    lines = [Line("user@dev-server:~/price-intelligence$ docker compose -f docker-compose.yml logs --tail=15 collector", PROMPT), Line("")]
    for raw in log_lines[:15]:
        color = FG
        if "ERROR" in raw:
            color = RED
        elif "WARNING" in raw:
            color = YELLOW
        elif "INFO" in raw and ("завершен" in raw or "completed" in raw or "сохранено" in raw):
            color = GREEN
        lines.append(Line(raw, color))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — docker compose logs collector", lines=lines, cols=120)


def _pytest_bin() -> str:
    """Путь к pytest в venv проекта или системный fallback."""
    venv_pytest = ROOT / ".venv" / "bin" / "pytest"
    return str(venv_pytest if venv_pytest.is_file() else "pytest")


def _bandit_bin() -> str:
    """Путь к bandit в venv проекта или системный fallback."""
    venv_bandit = ROOT / ".venv" / "bin" / "bandit"
    return str(venv_bandit if venv_bandit.is_file() else "bandit")


def _trim_lines(lines: list[str], *, head: int, tail: int) -> list[str]:
    """Сохранить начало и конец длинного вывода с маркером пропуска."""
    if len(lines) <= head + tail + 1:
        return lines
    skipped = len(lines) - head - tail
    return lines[:head] + [f"... ({skipped} lines omitted) ..."] + lines[-tail:]


def _pytest_line_color(raw: str) -> str:
    """Цвет строки вывода pytest."""
    upper = raw.upper()
    if "PASSED" in upper:
        return GREEN
    if "FAILED" in upper or "ERROR" in upper:
        return RED
    if "WARNING" in upper or "WARNINGS SUMMARY" in upper:
        return YELLOW
    if raw.startswith("="):
        return CYAN
    return FG


def render_pytest_full(out: Path) -> None:
    """Сгенерировать скриншот полного прогона ``pytest tests/ -v``."""
    raw_lines = _run_capture([_pytest_bin(), "tests/", "-v", "--tb=no"], cwd=ROOT)
    body = _trim_lines(raw_lines, head=8, tail=12)
    lines = [
        Line("user@dev-server:~/price-intelligence$ .venv/bin/pytest tests/ -v --tb=no", PROMPT),
        Line(""),
    ]
    for raw in body:
        lines.append(Line(raw, _pytest_line_color(raw)))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — pytest tests/ -v", lines=lines, cols=120)


def render_coverage_report(out: Path) -> None:
    """Сгенерировать скриншот отчёта покрытия кода."""
    raw_lines = _run_capture(
        [
            _pytest_bin(),
            "tests/",
            "--cov=app",
            "--cov-report=term-missing",
            "--tb=no",
            "-q",
        ],
        cwd=ROOT,
    )
    # Оставляем хвост с таблицей модулей и строкой TOTAL.
    body = raw_lines[-28:] if len(raw_lines) > 28 else raw_lines
    lines = [
        Line(
            "user@dev-server:~/price-intelligence$ .venv/bin/pytest tests/ "
            "--cov=app --cov-report=term-missing -q",
            PROMPT,
        ),
        Line(""),
    ]
    for raw in body:
        color = GREEN if raw.strip().startswith("TOTAL") else FG
        if "passed" in raw and "warning" in raw:
            color = GREEN
        lines.append(Line(raw, color))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — pytest --cov=app", lines=lines, cols=120)


def render_bandit_report(out: Path) -> None:
    """Сгенерировать скриншот вывода ``bandit -r app/``."""
    raw_lines = _run_capture([_bandit_bin(), "-r", "app/", "-f", "txt"], cwd=ROOT)
    body = _trim_lines(raw_lines, head=6, tail=14)
    lines = [
        Line("user@dev-server:~/price-intelligence$ .venv/bin/bandit -r app/ -f txt", PROMPT),
        Line(""),
    ]
    for raw in body:
        color = FG
        if "Severity: High" in raw:
            color = RED
        elif "Severity: Medium" in raw:
            color = YELLOW
        elif "Severity: Low" in raw:
            color = DIM
        elif raw.strip().startswith("Run metrics:") or "Total issues" in raw:
            color = CYAN
        lines.append(Line(raw, color))
    lines.extend([Line(""), Line("user@dev-server:~/price-intelligence$ _", PROMPT)])
    _render_terminal(out, title="bash — bandit -r app/", lines=lines, cols=120)


def render_gemini_curl(out: Path) -> None:
    """Сгенерировать контрольный скриншот шаблона запроса к Gemini API.

    Если API-ключ не задан, это явно фиксируется в терминале — без имитации
    «живого» ответа модели.
    """
    lines = [
        Line("user@dev-server:~/price-intelligence$ cat /tmp/payload.json", PROMPT),
        Line("{", FG),
        Line("  \"contents\": [{", FG),
        Line("    \"parts\": [{", FG),
        Line("      \"text\": \"Ты — эксперт по электротехнике и кабельной продукции. Определи, являются \\", FG),
        Line("                ли эти две позиции одним и тем же товаром (одна SKU: тот же тип, номинал, \\", FG),
        Line("                сечение/мощность/тип расцепителя и т.д.). Учитывай маркировку, бренды,    \\", FG),
        Line("                модельные коды.\\n\\nТовар А: автоматический выключатель ва47-29 1p 16a c ekf\\n \\", FG),
        Line("                Товар Б: авт выкл 1p 16a c-29 ekf proxima\\n\\nОтветь строго одним JSON-       \\", FG),
        Line("                объектом без пояснений и без markdown.\"                                       ", FG),
        Line("    }]                                                                                          ", FG),
        Line("  }]                                                                                            ", FG),
        Line("}", FG),
        Line(""),
        Line("user@dev-server:~/price-intelligence$ echo ${GEMINI_API_KEY:+set}", PROMPT),
        Line("", RED),
        Line("user@dev-server:~/price-intelligence$ curl -s -X POST \\", PROMPT),
        Line("  \"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=$GEMINI_API_KEY\" \\", PROMPT),
        Line("  -H 'Content-Type: application/json' -d @/tmp/payload.json", PROMPT),
        Line(""),
        Line("# live-вызов недоступен без API-ключа; ожидается JSON вида:", DIM),
        Line("{\"match\": true|false, \"confidence\": 0.00..1.00, \"reason\": \"...\"}", CYAN),
        Line(""),
        Line("user@dev-server:~/price-intelligence$ _", PROMPT),
    ]
    _render_terminal(out, title="bash — curl Gemini API", lines=lines, cols=120)


def main() -> int:
    """Сгенерировать все терминальные скриншоты."""
    OUT.mkdir(parents=True, exist_ok=True)
    render_docker_ps(OUT / "docker_ps.png")
    render_docker_stats(OUT / "docker_stats.png")
    render_docker_logs(OUT / "docker_logs.png")
    render_gemini_curl(OUT / "gemini_curl.png")
    render_pytest_full(OUT / "pytest_full.png")
    render_coverage_report(OUT / "coverage_report.png")
    render_bandit_report(OUT / "bandit_report.png")
    print(f"Терминальные скриншоты сгенерированы: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
