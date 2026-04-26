"""Локальный XLS: отсутствие пути / файла не трогает сессию."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.collectors.local_price_xls import (
    _effective_default_brand_for_path,
    _resolved_local_price_xls_path,
    fetch_local_price_xls,
)


def test_fetch_skips_when_env_path_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOCAL_PRICE_XLS_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    session = MagicMock()
    fetch_local_price_xls(session)
    assert session.commit.call_count == 0


def test_fetch_skips_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCAL_PRICE_XLS_PATH", str(tmp_path / "missing.xls"))
    session = MagicMock()
    fetch_local_price_xls(session)
    assert session.commit.call_count == 0


def test_resolved_path_prefers_env_over_cwd_zayavka(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCAL_PRICE_XLS_PATH", "/explicit/path.xls")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "zayavka77rybinsk.xls").touch()
    assert _resolved_local_price_xls_path() == "/explicit/path.xls"


def test_resolved_path_falls_back_to_cwd_zayavka(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOCAL_PRICE_XLS_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    z = tmp_path / "zayavka77rybinsk.xls"
    z.touch()
    assert _resolved_local_price_xls_path() == str(z)


def test_effective_brand_zayavka_is_tdm_when_env_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOCAL_PRICE_DEFAULT_BRAND", raising=False)
    p = tmp_path / "zayavka77rybinsk.xls"
    p.touch()
    assert _effective_default_brand_for_path(str(p)) == "TDM"


def test_effective_brand_other_file_none_without_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOCAL_PRICE_DEFAULT_BRAND", raising=False)
    p = tmp_path / "other.xls"
    p.touch()
    assert _effective_default_brand_for_path(str(p)) is None


def test_zayavka_sample_row_has_tdm_brand_if_repo_file_exists() -> None:
    """Смок на реальном zayavka77rybinsk.xls в корне репозитория (опционально)."""
    root = Path(__file__).resolve().parents[1]
    path = root / "zayavka77rybinsk.xls"
    if not path.is_file():
        pytest.skip("нет zayavka77rybinsk.xls в корне репо")
    from app.collectors.local_price_xls import rows_from_xls_path

    brand = _effective_default_brand_for_path(str(path))
    rows = rows_from_xls_path(str(path), default_brand=brand)
    assert len(rows) > 100
    assert any(r.get("brand") == "TDM" for r in rows[:80])
