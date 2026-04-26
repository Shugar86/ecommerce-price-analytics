"""
Эвристики для обнаружения аномалий в ряду цен.

Интерпретируемые пороговые правила: резкий скачок, паттерн «подняли перед скидкой»,
z-отклонение доходности — без тяжёлых нейросетевых моделей.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class AnomalyHit:
    """Описание одной обнаруженной аномалии."""

    anomaly_type: str
    severity: float
    detail: str
    price_at_detection: float


def detect_price_anomalies(
    prices: Sequence[float],
    *,
    spike_threshold: float = 0.22,
    fake_discount_prior_rise: float = 0.12,
    fake_discount_drop: float = 0.1,
    z_min: float = 2.2,
) -> list[AnomalyHit]:
    """Находит аномалии по последним точкам временного ряда цен.

    Args:
        prices: Цены по возрастанию времени (от старых к новым).
        spike_threshold: Порог относительного скачка между двумя последними точками.
        fake_discount_prior_rise: Минимальный рост перед «скидкой».
        fake_discount_drop: Минимальное падение после роста (доля).
        z_min: Порог |z| для доходности относительно недавней истории.

    Returns:
        Список срабатываний (может быть пустым).
    """
    if len(prices) < 2:
        return []

    p = np.array([float(x) for x in prices], dtype=float)
    last = float(p[-1])
    out: list[AnomalyHit] = []

    prev = float(p[-2])
    if prev > 1e-9:
        chg = (last - prev) / prev
        if abs(chg) >= spike_threshold:
            out.append(
                AnomalyHit(
                    anomaly_type="spike",
                    severity=float(min(1.0, abs(chg))),
                    detail=f"Скачок цены относительно предыдущей точки: {chg * 100:.1f}%",
                    price_at_detection=last,
                )
            )

    if len(p) >= 3:
        a, b, c = float(p[-3]), float(p[-2]), float(p[-1])
        if a > 1e-9 and b > 1e-9:
            rise = (b - a) / a
            drop = (c - b) / b
            if rise >= fake_discount_prior_rise and drop <= -fake_discount_drop:
                out.append(
                    AnomalyHit(
                        anomaly_type="fake_discount",
                        severity=float(min(1.0, rise + abs(drop))),
                        detail=(
                            "Паттерн «подняли перед снижением»: возможная маркетинговая "
                            f"«скидка» (рост {rise * 100:.1f}%, затем изменение {drop * 100:.1f}%)."
                        ),
                        price_at_detection=c,
                    )
                )

    if len(p) >= 4:
        window = p[-5:]
        rets: list[float] = []
        for i in range(1, len(window)):
            if window[i - 1] > 1e-9:
                rets.append(float((window[i] - window[i - 1]) / window[i - 1]))
        if len(rets) >= 2:
            arr = np.array(rets, dtype=float)
            mu = float(np.mean(arr[:-1]))
            sigma = float(np.std(arr[:-1]))
            last_ret = float(arr[-1])
            if sigma > 1e-9:
                z = abs((last_ret - mu) / sigma)
                if z >= z_min:
                    out.append(
                        AnomalyHit(
                            anomaly_type="zscore_return",
                            severity=float(min(1.0, z / 4.0)),
                            detail=f"Доходность последнего шага необычна относительно истории (z≈{z:.2f}).",
                            price_at_detection=last,
                        )
                    )

    return out
