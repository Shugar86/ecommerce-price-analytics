"""Smoke-тест HTTP API веб-сервиса без БД."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.web.main import app


def test_health_endpoint() -> None:
    """Эндпоинт /health не требует подключения к PostgreSQL."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
