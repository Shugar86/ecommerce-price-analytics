"""
Клиент Gemini для второго мнения по паре названий («серая» зона fuzzy).

При недоступности API возвращает dict с ключом ``error`` — вызывающий код должен
сохранить эвристический результат без сбоев пайплайна.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_EXPLAIN_TRUNC = 600
_SUMMARY_TRUNC = 1200

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*}", re.MULTILINE)


def _pair_cache_key(left: str, right: str) -> str:
    """Стабильный ключ кэша по паре строк (упорядоченный пайп для симметрии)."""
    la, lb = left.strip(), right.strip()
    if la <= lb:
        payload = f"{la}|{lb}"
    else:
        payload = f"{lb}|{la}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Вытаскивает первый JSON-объект из ответа модели."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # ```json ... ``` или ``` ... ```
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    match = _JSON_BLOCK_RE.search(cleaned)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_verdict(parsed: dict[str, Any]) -> dict[str, Any]:
    """Приводит ответ модели к единому контракту."""
    raw_match = parsed.get("match")
    match_ok: bool | None = None
    if isinstance(raw_match, bool):
        match_ok = raw_match
    elif isinstance(raw_match, str):
        low = raw_match.strip().lower()
        if low in ("true", "1", "yes", "да"):
            match_ok = True
        elif low in ("false", "0", "no", "нет"):
            match_ok = False

    conf_raw = parsed.get("confidence")
    confidence = 0.0
    if isinstance(conf_raw, (int, float)):
        confidence = float(conf_raw)
    elif isinstance(conf_raw, str):
        try:
            confidence = float(conf_raw.strip().replace(",", "."))
        except ValueError:
            confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = parsed.get("reason")
    reason_str = str(reason).strip() if reason is not None else ""

    if match_ok is None:
        return {
            "match": False,
            "confidence": confidence,
            "reason": reason_str,
            "error": "missing_or_invalid_match_field",
        }
    return {
        "match": bool(match_ok),
        "confidence": confidence,
        "reason": reason_str,
    }


class GeminiValidator:
    """
    Клиент Gemini: сопоставление пар названий («серая зона») и текстовые объяснения для UI.

    Кэширует ответы в памяти процесса по ключам задач (пары SKU, anomaly_id и т.д.).
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        """
        Args:
            api_key: Ключ ``GOOGLE_API_KEY`` (пустая строка = клиент недоступен).
            model_name: Имя модели Gemini.
        """
        self._api_key = (api_key or "").strip() or None
        self._model_name = (model_name or "gemini-2.5-flash").strip()
        self._cache: dict[str, dict[str, Any]] = {}
        """Кэш ``validate_pair``: md5 ключ → вердикт JSON."""
        self._text_cache: dict[str, str] = {}
        """Кэш свободного текста: explain_anomaly / forecast / summaries."""

    @property
    def is_configured(self) -> bool:
        """True, если задан ключ API."""
        return self._api_key is not None

    def validate_pair(self, name_a: str, name_b: str) -> dict[str, Any]:
        """
        Спрашивает модель, одна ли это номенклатурная позиция.

        Args:
            name_a: Наименование слева (как в БД).
            name_b: Наименование справа.

        Returns:
            Словарь с полями ``match``, ``confidence``, ``reason`` или ``error``.
        """
        left = str(name_a or "").strip()
        right = str(name_b or "").strip()
        if not left or not right:
            return {"match": False, "confidence": 0.0, "reason": "", "error": "empty_name"}

        if not self._api_key:
            return {"match": False, "confidence": 0.0, "reason": "", "error": "missing_api_key"}

        key = _pair_cache_key(left, right)
        if key in self._cache:
            return dict(self._cache[key])

        try:
            import google.generativeai as genai
        except ImportError as exc:
            logger.warning("google-generativeai не установлен: %s", exc)
            result = {"match": False, "confidence": 0.0, "reason": "", "error": "import_error"}
            self._cache[key] = result
            return dict(result)

        prompt = (
            "Ты — эксперт по электротехнике и кабельной продукции. "
            "Определи, являются ли эти две позиции одним и тем же товаром "
            "(одна SKU: тот же тип, номинал, сечение/мощность/тип расцепителя и т.д.). "
            "Учитывай маркировку, бренды, модельные коды.\n\n"
            f"Товар А: {left}\n"
            f"Товар Б: {right}\n\n"
            "Ответь строго одним JSON-объектом без пояснений и без markdown: "
            '{"match": boolean, "confidence": number от 0 до 1, "reason": string}'
        )

        genai.configure(api_key=self._api_key)
        try:
            model = genai.GenerativeModel(self._model_name)
            response = model.generate_content(prompt)
        except Exception as exc:
            logger.warning("Gemini API error: %s", exc)
            result = {"match": False, "confidence": 0.0, "reason": "", "error": "api_error"}
            self._cache[key] = result
            return dict(result)

        text = getattr(response, "text", None) or ""
        if not str(text).strip():
            blocks = getattr(response, "candidates", None)
            logger.warning(
                "Пустой ответ Gemini (%s candidates=%s)",
                self._model_name,
                len(blocks or []),
            )
            result = {"match": False, "confidence": 0.0, "reason": "", "error": "empty_response"}
            self._cache[key] = result
            return dict(result)

        parsed = _extract_json_object(str(text))
        if parsed is None:
            logger.warning("Не удалось разобрать JSON из ответа Gemini: %s", text[:240])
            result = {"match": False, "confidence": 0.0, "reason": "", "error": "bad_json"}
            self._cache[key] = result
            return dict(result)

        verdict = _normalize_verdict(parsed)
        if verdict.get("error"):
            self._cache[key] = verdict
            return dict(verdict)

        logger.info(
            "Gemini verdict pair=%s match=%s confidence=%.3f",
            key[:8],
            verdict["match"],
            float(verdict["confidence"]),
        )
        self._cache[key] = verdict
        return dict(verdict)

    def _generate_plain_text(
        self,
        prompt: str,
        *,
        cache_key: str | None = None,
        max_len: int | None = None,
    ) -> str | None:
        """Вызывает модель для свободного текста с опциональным кэшем."""
        if not self._api_key:
            return None
        limit = max_len if max_len is not None else _EXPLAIN_TRUNC
        ck = cache_key.strip() if cache_key else None
        if ck and ck in self._text_cache:
            return self._text_cache[ck]

        try:
            import google.generativeai as genai
        except ImportError as exc:
            logger.warning("google-generativeai не установлен: %s", exc)
            return None

        genai.configure(api_key=self._api_key)
        try:
            model = genai.GenerativeModel(self._model_name)
            response = model.generate_content(prompt)
        except Exception as exc:
            logger.warning("Gemini API error (plain text): %s", exc)
            return None

        text = getattr(response, "text", None) or ""
        cleaned = self._squash_whitespace(str(text).strip())
        if not cleaned:
            logger.warning("Пустой текстовый ответ Gemini.")
            return None
        out = cleaned[:limit]
        if ck:
            self._text_cache[ck] = out
        return out

    @staticmethod
    def _squash_whitespace(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def explain_anomaly(
        self,
        *,
        anomaly_id: int | str,
        anomaly_type: str,
        product_name: str,
        detail: str | None,
        price_at_detection: float | None,
        price_series_tail: list[float] | None = None,
    ) -> str | None:
        """
        Кратко объясняет срабатывание эвристики аномалии для аналитика (1–2 предложения).

        Args:
            anomaly_id: Уникальный id записи для кэша.
            anomaly_type: Например spike / fake_discount / zscore_return.
            product_name: Название товара.
            detail: Текст детектора из БД.
            price_at_detection: Цена в момент срабатывания.
            price_series_tail: Хвост ряда цен (до ~8 последних значений).

        Returns:
            Текст объяснения или None при отключении / ошибке.
        """
        ck = f"anom_expl:{int(anomaly_id)}"
        if ck in self._text_cache:
            return self._text_cache[ck]

        tail_txt = ""
        if price_series_tail:
            trimmed = price_series_tail[-8:]
            tail_txt = f" Последние значения цены в рублях в ряд: {'; '.join(f'{x:.2f}' for x in trimmed)}."

        pt = ""
        if price_at_detection is not None:
            pt = f" Цена при срабатывании {float(price_at_detection):.2f} ₽."

        prompt = (
            "Ты — аналитик цен в сегменте электротехники (Россия/B2B). "
            "Объясни одному-двумя короткими предложениями на русском, что означает срабатывание "
            "детектора аномалии для аналитика (без технического жаргона статистики, если можно просто)."
            "\n\n"
            f"Тип детектора (как в коде): {str(anomaly_type or '')}\n"
            f"Товар: {str(product_name or '')[:420]}\n"
            f"Детали детектора: {str(detail or '—')[:800]}"
            f"{tail_txt}"
            f"{pt}\n\n"
            "Ответь только текстом, без заголовков, без markdown, без нумерации."
        )

        return self._generate_plain_text(prompt, cache_key=ck)

    def summarize_anomalies_recent(self, briefing_lines: str, *, cache_key: str) -> str | None:
        """
        Суммирует недавний список аномалий для карточки «AI-помощник».

        Args:
            briefing_lines: Текст с перечнем строк (до ~12 кейсов).
            cache_key: Стабильный ключ для кэша по составу набора ids.

        Returns:
            Абзац 3–6 предложений или None.
        """
        ck = f"sum_anom:{cache_key}"
        if ck in self._text_cache:
            return self._text_cache[ck]

        prompt = (
            "Ты — руководитель ценового мониторинга (электротехника, РФ). "
            "По следующему краткому логу последних алертов (до 48 ч) напиши 3–6 предложений на русском для комиссии: "
            "какая общая картина, какие два типа рисков важнее, что проверить в первую очередь.\n\n"
            f"{briefing_lines[:6000]}\n\n"
            "Только текст, без маркдовна и списков с дефисами (можешь использовать точки)."
        )

        txt = self._generate_plain_text(prompt, cache_key=ck, max_len=_SUMMARY_TRUNC)
        if txt and len(txt) > _SUMMARY_TRUNC:
            shorter = txt[:_SUMMARY_TRUNC].rsplit(".", 1)
            txt = (shorter[0] + ".") if len(shorter) > 1 and shorter[0] else txt[:_SUMMARY_TRUNC]
            self._text_cache[ck] = txt
        elif txt:
            self._text_cache[ck] = txt
        return txt

    def explain_forecast(
        self,
        *,
        product_name: str,
        last_price: float,
        forecast_price: float,
        horizon_label: str,
    ) -> str | None:
        """
        Одно-два предложения: что может означать линейный прогноз для аналитика.

        Args:
            product_name: Название товара.
            last_price: Последняя известная цена из истории.
            forecast_price: Прогноз на следующую точку.
            horizon_label: Подпись горизонта (дата текстом).

        Returns:
            Краткий нарратив или None.
        """
        ck_raw = hashlib.md5(
            f"fcast|{(product_name or '')[:240]}|{last_price}|{forecast_price}|{horizon_label}".encode(
                "utf-8"
            )
        ).hexdigest()
        ck = f"fcast_expl:{ck_raw}"
        prompt = (
            "Ты — аналитик цен электротехники (РФ). "
            "По упрощённому линейному прогнозу напиши 1–2 предложения на русском для дашборда: "
            "как трактовать цифру, какие ограничения у линейного тренда. "
            "Не давай финансовых советов («покупай/продавай»), только наблюдение.\n\n"
            f"Товар: {str(product_name or '')[:380]}\n"
            f"Последняя цена: {last_price:.2f} ₽.\n"
            f"Прогноз: {forecast_price:.2f} ₽ ({horizon_label}).\n\n"
            "Только текст, без markdown."
        )
        return self._generate_plain_text(prompt, cache_key=ck)


_web_validator_singleton: GeminiValidator | None = None


def gemini_validator_from_env() -> GeminiValidator | None:
    """
    Общая фабрика для веб-объяснений: достаточно ``GOOGLE_API_KEY`` в окружении.

    Отдельно от флага ``ENABLE_GEMINI_VALIDATION`` воркера, чтобы включать нарративы
    на /alerts и карточке товара без включения Gemini в конвейере сопоставления.

    Кэш ответов хранится в singleton-экземпляре между запросами uvicorn-worker'а.

    Returns:
        Настроенный клиент или ``None``, если ключ не задан.
    """
    global _web_validator_singleton
    key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        return None
    if _web_validator_singleton is None:
        model_name = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
        _web_validator_singleton = GeminiValidator(
            api_key=key,
            model_name=model_name or "gemini-2.5-flash",
        )
    if not _web_validator_singleton.is_configured:
        return None
    return _web_validator_singleton
