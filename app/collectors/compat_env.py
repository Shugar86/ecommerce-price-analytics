"""Чтение int из os.environ: пустая строка (часто из docker-compose) = default."""

from __future__ import annotations

import os


def env_int(name: str, default: int) -> int:
    """Возвращает int или ``default``, если переменная не задана или пуста."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip(), 10)
