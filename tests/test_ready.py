"""Тест эндпоинта готовности (/ready)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.web.main import app


@patch("app.web.main.dispose_engine", MagicMock())
@patch("app.web.main.init_db", MagicMock())
@patch("app.web.main.get_engine")
def test_ready_ok_when_database_responds(mock_get_engine: MagicMock) -> None:
    """При успешном SELECT 1 возвращается 200 и статус ready."""
    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_cm
    mock_get_engine.return_value = mock_engine

    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


@patch("app.web.main.dispose_engine", MagicMock())
@patch("app.web.main.init_db", MagicMock())
@patch("app.web.main.get_engine")
def test_ready_503_when_database_fails(mock_get_engine: MagicMock) -> None:
    """При ошибке БД — 503."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = OSError("connection refused")
    mock_get_engine.return_value = mock_engine

    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "database_unavailable"
