"""Тесты разбора ответа GeminiValidator без сетевых вызовов."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import app.llm.gemini_validator as gemini_mod
from app.llm.gemini_validator import (
    GeminiValidator,
    _extract_json_object,
    _normalize_verdict,
    gemini_validator_from_env,
)


def test_extract_json_from_fenced_block() -> None:
    """JSON внутри markdown-ограждения извлекается."""
    text = '```json\n{"match": true, "confidence": 0.9, "reason": "ok"}\n```'
    parsed = _extract_json_object(text)
    assert parsed is not None
    assert parsed["match"] is True


def test_normalize_verdict_string_match() -> None:
    """Строковые значения match приводятся к bool."""
    v = _normalize_verdict({"match": "да", "confidence": "0.85", "reason": "тест"})
    assert "error" not in v
    assert v["match"] is True
    assert pytest.approx(v["confidence"], rel=1e-6) == 0.85


def test_validate_pair_returns_error_without_key() -> None:
    """Без API-ключа возвращается контролируемая ошибка."""
    client = GeminiValidator(api_key=None)
    out = client.validate_pair("товар А", "товар Б")
    assert out.get("error") == "missing_api_key"


@patch("app.llm.gemini_validator.logger")
def test_validate_pair_calls_api_and_parses(mock_log: MagicMock) -> None:
    """При успешном ответе API возвращается структурированный вердикт."""
    fake_response = MagicMock()
    fake_response.text = '{"match": false, "confidence": 0.2, "reason": "different sizes"}'

    genai_mod = types.ModuleType("google.generativeai")
    genai_mod.configure = MagicMock()
    fake_model_cls = MagicMock()
    fake_model_cls.return_value.generate_content.return_value = fake_response
    genai_mod.GenerativeModel = fake_model_cls

    google_mod = types.ModuleType("google")
    google_mod.generativeai = genai_mod  # type: ignore[attr-defined]

    old_google = sys.modules.get("google")
    old_genai = sys.modules.get("google.generativeai")
    sys.modules["google"] = google_mod
    sys.modules["google.generativeai"] = genai_mod

    try:
        client = GeminiValidator(api_key="fake-key-local-test")
        out = client.validate_pair("Cable 3x2.5", "Cable 3x1.5")
    finally:
        if old_google is not None:
            sys.modules["google"] = old_google
        else:
            sys.modules.pop("google", None)
        if old_genai is not None:
            sys.modules["google.generativeai"] = old_genai
        else:
            sys.modules.pop("google.generativeai", None)

    assert out["match"] is False
    assert pytest.approx(out["confidence"], rel=1e-6) == 0.2
    mock_log.warning.assert_not_called()


def test_gemini_validator_from_env_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без ключа фабрика веб-клиента возвращает None и не оставляет висящий singleton."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    gemini_mod._web_validator_singleton = None
    assert gemini_validator_from_env() is None


def _install_fake_google_genai(response_text: str) -> None:
    fake_response = MagicMock()
    fake_response.text = response_text

    genai_mod = types.ModuleType("google.generativeai")
    genai_mod.configure = MagicMock()
    fake_model_cls = MagicMock()
    fake_model_cls.return_value.generate_content.return_value = fake_response
    genai_mod.GenerativeModel = fake_model_cls

    google_mod = types.ModuleType("google")
    google_mod.generativeai = genai_mod  # type: ignore[attr-defined]

    sys.modules["google"] = google_mod
    sys.modules["google.generativeai"] = genai_mod


def _restore_google_modules(
    old_google: types.ModuleType | None, old_genai: types.ModuleType | None
) -> None:
    if old_google is not None:
        sys.modules["google"] = old_google
    else:
        sys.modules.pop("google", None)
    if old_genai is not None:
        sys.modules["google.generativeai"] = old_genai
    else:
        sys.modules.pop("google.generativeai", None)


def test_explain_anomaly_calls_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Краткое объяснение аномалии приходит из ответа модели."""
    old_google = sys.modules.get("google")
    old_genai = sys.modules.get("google.generativeai")
    _install_fake_google_genai("Цена резко выросла относительно предыдущей точки истории.")
    try:
        gemini_mod._web_validator_singleton = None
        client = GeminiValidator(api_key="k", model_name="gemini-test")
        txt = client.explain_anomaly(
            anomaly_id=91001,
            anomaly_type="spike",
            product_name="Автомат 1P 16A",
            detail="delta=0.24 prev=1200 now=1490",
            price_at_detection=1490.0,
            price_series_tail=[1200.0, 1490.0],
        )
    finally:
        _restore_google_modules(old_google, old_genai)
        gemini_mod._web_validator_singleton = None

    assert txt is not None
    assert "Цена" in txt


def test_explain_anomaly_empty_response_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой ответ API не ломает страницу и даёт None."""
    old_google = sys.modules.get("google")
    old_genai = sys.modules.get("google.generativeai")
    fake_response = MagicMock()
    fake_response.text = "   "

    genai_mod = types.ModuleType("google.generativeai")
    genai_mod.configure = MagicMock()
    fake_model_cls = MagicMock()
    fake_model_cls.return_value.generate_content.return_value = fake_response
    genai_mod.GenerativeModel = fake_model_cls

    google_mod = types.ModuleType("google")
    google_mod.generativeai = genai_mod  # type: ignore[attr-defined]
    sys.modules["google"] = google_mod
    sys.modules["google.generativeai"] = genai_mod

    try:
        client = GeminiValidator(api_key="k", model_name="gemini-test")
        txt = client.explain_anomaly(
            anomaly_id=91002,
            anomaly_type="zscore_return",
            product_name="X",
            detail="z=3",
            price_at_detection=10.0,
            price_series_tail=None,
        )
    finally:
        _restore_google_modules(old_google, old_genai)

    assert txt is None


def test_summarize_anomalies_recent_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сводка по списку алертов возвращает текст модели."""
    old_google = sys.modules.get("google")
    old_genai = sys.modules.get("google.generativeai")
    _install_fake_google_genai(
        "Преобладают скачки цен после роста спроса и отдельные ложные скидки. "
        "Проверьте топ-товары вручную."
    )
    try:
        client = GeminiValidator(api_key="k", model_name="gemini-test")
        s1 = client.summarize_anomalies_recent("id=1 spike", cache_key="ckdemo")
        s2 = client.summarize_anomalies_recent("DIFFERENT BRIEF", cache_key="ckdemo")
    finally:
        _restore_google_modules(old_google, old_genai)

    assert s1 == s2
    assert "скачки" in (s1 or "")


def test_explain_forecast_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Нарратив к прогнозу строится по ответу модели."""
    old_google = sys.modules.get("google")
    old_genai = sys.modules.get("google.generativeai")
    _install_fake_google_genai(
        "Линейный тренд показывает ориентировочное направление, но игнорирует сезонность."
    )
    try:
        client = GeminiValidator(api_key="k", model_name="gemini-test")
        out = client.explain_forecast(
            product_name="Клемма",
            last_price=100.0,
            forecast_price=105.5,
            horizon_label="06.05.2026",
        )
    finally:
        _restore_google_modules(old_google, old_genai)

    assert out is not None
    assert "Линейный" in out
