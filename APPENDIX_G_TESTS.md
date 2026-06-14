# Приложение Г — Автоматические тесты и трассировка к требованиям ТЗ

Настоящее приложение дополняет подразделы **2.5** и **3.1** пояснительной записки: фиксирует состав автоматического тестового комплекта, матрицу трассировки к функциональным требованиям (§1.4.3, табл. 2.4) и листинги ключевых тест-кейсов. Полный исходный код — каталог `tests/` репозитория прототипа (22 модуля, **77** функций `test_*` на дату прогона).

---

## Г.1 Воспроизведение прогона

Команды выполняются из корня проекта после создания виртуального окружения:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest-cov bandit

# Полный прогон (рисунок Г.1)
.venv/bin/pytest tests/ -v --tb=no

# Покрытие кода (рисунок Г.2)
.venv/bin/pytest tests/ --cov=app --cov-report=term-missing -q

# Статический анализ безопасности (рисунок Г.3)
.venv/bin/bandit -r app/ -f txt

# Генерация «скриншотов терминала» (Pillow)
.venv/bin/python tools/build_terminal_screens.py
```

**Результат прогона (2026-06-03):** 77 passed, 0 failed; суммарное покрытие `app/` — **40 %** (скрипты отчётов и CLI-утилиты без unit-тестов снижают средний процент; ядро matching/ML/collector покрыто выше).

---

## Г.2 Скриншоты подтверждения

![](assets/screenshots/pytest_full.png)
**Рисунок Г.1** — Результат выполнения `pytest tests/ -v`: полный тестовый комплект (77 тестов).

![](assets/screenshots/coverage_report.png)
**Рисунок Г.2** — Покрытие кода: `pytest --cov=app --cov-report=term-missing`.

![](assets/screenshots/bandit_report.png)
**Рисунок Г.3** — Вывод `bandit -r app/`. Находки уровня High связаны с использованием MD5 для **ключей кэша** LLM-ответов (не для криптографии); критичных уязвимостей, блокирующих демонстрацию прототипа, не выявлено.

![](assets/screenshots/pytest_anomalies.png)
**Рисунок Г.4** — Фрагмент модульного прогона детектора аномалий (см. листинг Г.1).

---

## Г.3 Матрица трассировки: требования ТЗ → тесты

Таблица Г.1 — Матрица трассировки функциональных требований ТЗ к автоматическим тестам.

| № ТЗ | Требование | Уровень ISTQB | Тестовый модуль / артефакт | Ключевые функции |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Автоматический опрос источников | интеграционный | `test_carreta_collector.py`, `test_local_price_xls.py`, `test_source_pairs.py` | парсинг XLS/YML, конфиг пар источников |
| 2 | История изменений цен | интеграционный | `test_barcode_enrich.py`, `test_price_diff.py` | UPSERT normalized_offers, diff двух источников |
| 3а | Медианы и отклонения | модульный + интегр. | `test_kpi_engine.py`, `test_price_intelligence_db.py` | floor, price index, raise/lower |
| 3б | Детектирование аномалий | модульный | `test_anomalies.py` | spike, плоский ряд |
| 3в | Прогнозирование (линейный тренд) | модульный | `test_gemini_validator.py` | `test_explain_forecast_returns_text` |
| 4а | Exact: barcode / vendor_code | модульный | `test_matching_v2.py` | `test_barcode_beats_titles`, `test_vendor_brand_pair` |
| 4б | Fuzzy + TF-IDF + confidence | модульный | `test_matching.py`, `test_tfidf_pairs.py`, `test_matching_v2.py` | Jaccard, TF-IDF, `test_fuzzy_is_not_automated` |
| 4в | Ручное подтверждение / отклонение | модульный | `test_matching_v2.py` | fuzzy помечается `is_automated=False` |
| 4г | AI-валидация (JSON-контракт) | модульный | `test_gemini_validator.py` | парсинг JSON, нормализация verdict |
| 5а | Графики Chart.js | системный | скриншот `product_card.png` (глава 2) | UI без headless-теста |
| 5б | Панель качества данных | системный | скриншот `dashboard.png` | UI |
| 5в | `/ru-benchmark` | интеграционный | `test_ru_matching_benchmark.py`, `test_defense_visuals.py` | эталон RuEcom-2026, PNG |
| 6а–6в | Telegram-бот | системный | приложение Б, `test_product_search.py` | поиск по `name_norm` |
| — | Health / readiness API | дымовой | `test_web_health.py`, `test_ready.py` | `/health`, `/ready` |
| — | Аудит источников | интеграционный | `test_source_audit.py`, `test_health_stats.py` | usable_score |
| — | Нагрузочное (k6, 200 VU) | системный | `tools/k6_loadtest.js`, рис. 2.25 | не pytest |
| — | Безопасность (bandit) | статический | рисунок Г.3 | SAST |

**Вывод.** Все 15 функциональных требований табл. 2.4 имеют подтверждение в коде; для пунктов 5а–5б и 6а–6в дополнительно зафиксированы скриншоты UI (глава 2, приложение Б). Алгоритмические требования (3б, 4а–4г) покрыты модульными pytest-тестами из таблицы Г.1.

---

## Г.4 Сводная таблица тестовых модулей

Таблица Г.2 — Сводный перечень тестовых модулей pytest.

| Модуль | Тестов | Проверяемый компонент |
| :--- | :---: | :--- |
| `test_anomalies.py` | 2 | `app/ml/anomalies.py` |
| `test_name_normalization.py` | 3 | `app/ml/name_normalization.py` |
| `test_matching.py` | 8 | `app/matching/text.py` |
| `test_matching_v2.py` | 5 | `app/ml/matching.py` |
| `test_tfidf_pairs.py` | 3 | `app/ml/tfidf_pairs.py` |
| `test_kpi_engine.py` | 4 | KPI-формулы price intelligence |
| `test_price_intelligence_db.py` | 2 | `app/analytics/price_intelligence.py` + SQLite |
| `test_gemini_validator.py` | 9 | `app/llm/gemini_validator.py` |
| `test_web_health.py` | 1 | `GET /health` |
| `test_ready.py` | 2 | `GET /ready` |
| `test_ru_matching_benchmark.py` | 3 | эталон RuEcom-2026 |
| `test_carreta_collector.py` | 4 | парсер CARRETA XLS |
| `test_local_price_xls.py` | 7 | парсер TDM XLS |
| `test_barcode_enrich.py` | 2 | обогащение штрихкодами |
| `test_product_search.py` | 3 | поиск товаров |
| `test_source_pairs.py` | 8 | конфигурация пар источников |
| `test_ai_match_caps.py` | 3 | лимиты AI-сопоставления |
| `test_price_diff.py` | 1 | сравнение цен |
| `test_health_stats.py` | 1 | формула usable_score |
| `test_source_audit.py` | 1 | аудит источников |
| `test_openfoodfacts_reference.py` | 3 | справочник OpenFoodFacts |
| `test_defense_visuals.py` | 2 | визуализации защиты |

**Итого:** 22 модуля, 77 тестов. CI (`.github/workflows/ci.yml`) запускает `pytest tests/ -q` при каждом push/PR.

---

## Г.5 Листинги ключевых тест-кейсов

### Листинг Г.1 — Детектор ценовых аномалий (`tests/test_anomalies.py`)

```python
"""Тесты детектора ценовых аномалий."""

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
```

*Трассировка:* требование **3б** (табл. 2.4); рисунок 2.16а, рисунок Г.4.

---

### Листинг Г.2 — Дымовой тест веб-API (`tests/test_web_health.py`)

```python
"""Smoke-тест HTTP API веб-сервиса без БД."""

from fastapi.testclient import TestClient
from app.web.main import app


def test_health_endpoint() -> None:
    """Эндпоинт /health не требует подключения к PostgreSQL."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

*Трассировка:* дымовой уровень ISTQB (табл. 3.1); подраздел 2.5.1.

---

### Листинг Г.3 — Приоритет exact-сопоставления (`tests/test_matching_v2.py`, фрагмент)

```python
from app.ml.matching import is_fuzzy_for_review_only, match_pair


def test_barcode_beats_titles() -> None:
    """Одинаковый штрихкод даёт exact_barcode даже при разных названиях."""
    a = {"barcode": "4606050300105", "name": "A", "brand": "X", "vendor_code": "1"}
    b = {"barcode": "460 6050 300105", "name": "B", "brand": "Y", "vendor_code": "2"}
    r = match_pair(a, b)
    assert r is not None
    assert r.kind == "exact_barcode"
    assert r.is_automated is True
    assert r.confidence == 1.0


def test_fuzzy_is_not_automated() -> None:
    """Fuzzy only для ревью."""
    assert is_fuzzy_for_review_only("fuzzy_tfidf") is True
    a = {"barcode": None, "name": "Автомат однополюсный 10А C", ...}
    b = {"barcode": None, "name": "Автомат 10A C однополюс", ...}
    r = match_pair(a, b)
    assert r.kind == "fuzzy_jaccard"
    assert r.is_automated is False
```

*Трассировка:* требования **4а**, **4б**, **4в** (табл. 2.4).

---

### Листинг Г.4 — TF-IDF сопоставление (`tests/test_tfidf_pairs.py`, фрагмент)

```python
from app.ml.tfidf_pairs import filter_greedy_one_to_one, find_cross_shop_pairs


def test_similar_russian_names_high_score() -> None:
    """Близкие строки должны получить заметный score."""
    a = ["Переходник E14-GU10 белый TDM"]
    b = ["Переходник E14 GU10 белый EKF Proxima"]
    pairs = find_cross_shop_pairs(a, b, min_score=0.15, max_pairs=5)
    assert pairs
    assert pairs[0].score >= 0.15


def test_greedy_one_to_one_respects_unique_indices() -> None:
    """Greedy matching does not reuse the same catalog row on either side."""
    raw = find_cross_shop_pairs(a, b, min_score=0.01, max_pairs=50)
    slim = filter_greedy_one_to_one(raw)
    assert len({p.idx_a for p in slim}) == len(slim)
```

*Трассировка:* требование **4б** (TF-IDF, порог уверенности).

---

### Листинг Г.5 — KPI price intelligence на SQLite (`tests/test_price_intelligence_db.py`, фрагмент)

```python
def test_position_raise_price_below_floor(pi_session) -> None:
    """Наша цена ниже floor → raise_price (медиана по всем офферам каноникала)."""
    s.add(NormalizedOffer(source_name="EKF YML", price_rub=50.0, ...))
    s.add(NormalizedOffer(source_name="TDM Electric", price_rub=100.0, ...))
    pos = position_for_canonical(s, cp.id, our_price=45.0)
    assert pos.recommendation == "raise_price"
```

*Трассировка:* требование **3а** (медианы, отклонения, рекомендации).

---

### Листинг Г.6 — JSON-контракт AI-валидации (`tests/test_gemini_validator.py`, фрагмент)

```python
from app.llm.gemini_validator import _extract_json_object, _normalize_verdict, GeminiValidator


def test_extract_json_from_fenced_block() -> None:
    text = '```json\n{"match": true, "confidence": 0.9, "reason": "ok"}\n```'
    parsed = _extract_json_object(text)
    assert parsed["match"] is True


def test_validate_pair_returns_error_without_key() -> None:
    client = GeminiValidator(api_key=None)
    out = client.validate_pair("товар А", "товар Б")
    assert out.get("error") == "missing_api_key"
```

*Трассировка:* требование **4г** (JSON-ответ без markdown, контролируемая ошибка без ключа).

---

### Листинг Г.7 — Эталон RuEcom-2026 (`tests/test_ru_matching_benchmark.py`, фрагмент)

```python
def test_build_ru_matching_pairs_has_positive_and_hard_negative() -> None:
    """Exact vendor+brand creates label=1; same brand/different code creates label=0."""
    pairs = build_ru_matching_pairs(offers, max_positive_pairs=10, ...)
    assert any(p.label == 1 and p.label_source == "exact_vendor_brand" for p in pairs)
    assert any(p.label == 0 and p.label_source.startswith("hard_negative") for p in pairs)
    assert all(p.left_source != p.right_source for p in pairs)
```

*Трассировка:* требование **5в**, контрольный эксперiment §3.2 (без data leakage).

---

*Конец приложения Г.*
