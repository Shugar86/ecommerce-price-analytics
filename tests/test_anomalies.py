"""Тесты детектора ценовых аномалий."""

from __future__ import annotations

from app.ml.anomalies import detect_price_anomalies


def test_spike_detected() -> None:
    """Резкий рост цены должен давать тип spike."""
    hits = detect_price_anomalies([100.0, 100.0, 150.0], spike_threshold=0.2)
    types = {h.anomaly_type for h in hits}
    assert "spike" in types


def test_no_hit_on_flat_series() -> None:
    """Плоский ряд без сильных изменений не должен давать spike."""
    hits = detect_price_anomalies([10.0, 10.01, 10.02], spike_threshold=0.25)
    assert not any(h.anomaly_type == "spike" for h in hits)
