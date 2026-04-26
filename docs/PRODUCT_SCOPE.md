# Контекст продукта: цены и сопоставление

Документ фиксирует **согласованный объём (B + C)**: полуавтоматическое сопоставление **как кандидаты** + мониторинг прайс-листов, качество данных и метрики **exact**-покрытия. См. обоснование в обсуждении архитектуры репозитория.

## Что система **не** обещает

- **Полностью автоматическое** объединение каталогов в глобальные SKU без ошибок.
- Тождество товаров **только** на основании косинусной близости TF‑IDF по названиям.
- Один и тот же числовой порог сопоставимости «для всех» категорий без валидации на размеченных данных.

## Что система **делает**

- Сбор и нормализация прайсов (`app/collector.py`, в т.ч. EKF, TDM, **Complect-Service**, **Syperopt**), запись в **`normalized_offers`** и обновление **`source_health`**. Устаревший контур `products` сохраняется на переходный период. **Price intelligence** (`app/analytics/price_intelligence.py`): mediana, **price index**, эвристика COGS и floor-маржи, рекомендуемое действие; UI: `/`, `/market`, `/sources`. **Сопоставление v2** (`app/ml/matching.py`): сначала штрихкод, brand+артикул, артикул+category, brand+модель; **TF‑IDF** — только кандидаты ручного ревью, не для автозакреплений. FakeStore **не** входит в демо-цикл (только `ENABLE_FAKESTORE=1`).
- **Канонизация** (`app/analytics/canonical_sync.py`): кластеры офферов строятся только по **автоматическим** правилам `match_pair` (без fuzzy); при 2+ источниках создаётся `canonical_products`, поле `match_confidence` — максимум уверенности по парам в кластере. Опционально **обогащение** пустых brand/vendor из таблицы **`barcode_reference`** (Tier B; загрузка `python -m app.tools.load_barcode_reference`).
- Исторически: история цен, аномалии, прогноз, сопоставления `products` (`product_matches`).
- **Основная очередь ревью** — пары **`normalized_offers`** (`normalized_offer_matches`): fuzzy из `match_pair` между **несколькими** парами источников, задаваемыми в **`AI_MATCH_SOURCE_PAIRS`** (формат: `A|B;C|D` — точка с запятой между парами). Если переменная пуста — одна пара из **`AI_MATCH_NORMALIZED_LEFT` / `RIGHT`** (по умолчанию **EKF YML** ↔ **TDM Electric**; это *не* «центр продукта», а обратная совместимость). **KPI «наш» прайс:** `OUR_PRICING_SOURCE` или первая запись `OUR_PRICING_SOURCE_PRIORITY`. **Tier A (ETL):** все B2B-фиды; **Tier B:** `barcode_reference` (CSV, zip Catalog.app — `app.tools.fetch_barcode_reference_catalog`), опционально API `barcodes-catalog` при `ENABLE_BARCODES_CATALOG_API`. **Tier C (OWWA):** таблица `owwa_listings`, `ENABLE_OWWA`, заглушка до полного контракта API. **source_health** хранит `last_error` и длительность загрузки. Legacy: **кандидаты** по таблице `products` на **TF‑IDF + косинус** только при **`USE_LEGACY_PRODUCT_MATCHING=1`**. Записи помечаются `match_kind='fuzzy_tfidf'`, `match_status='suggested'` до ревью.
- Ручной **ревью** в веб-интерфейсе: кандидат может быть **подтверждён** или **отклонён**. Подтверждённые и отклонённые записи **не** пересчитываются при следующем цикле `ai_worker` (пересчитываются только `suggested` + `fuzzy_tfidf`).
- На дашборде: **полнота** полей `barcode`, `vendor_code`, `category_id`, `name_norm` и **число точных пересечений** ключей между парами магазинов (см. `app/quality/coverage.py`, аналогично `python -m app.overlap_report`).

## Терминология для внешних текстов (README, ВКР, тезисы)

- Использовать: **«мониторинг цен»**, **«сопоставление-кандидаты»**, **«по сходству наименований»**, **«подтверждение аналитиком»**.
- Не использовать как факт: **«движок автоматического сопоставления товаров»** без оговорок.
- Краткая формулировка: *«**Интеллектуальная аналитика цен** с **ассистированным** выравниванием позиций между поставщиками — **не** автономный entity resolution.»*
- Более развёрнуто: *«Система ведёт несколько прайс-листов, строит историю цен и **показывает** потенциальные связи между позициями. **Высокая уверенность** возможна лишь при **совпадении устойчивых ключей** (например штрихкод при корректных данных). **Сходство по названию** (TF‑IDF / токены) даёт **кандидатов на проверку**, а не утверждение о единой сущности товара.»*

## Ссылка на реализацию

| Кусок | Файл |
|-------|------|
| Цикл кандидатов (офферы + опционально products) | `app/ai_worker.py` |
| Очередь ревью по офферам | `normalized_offer_matches`, миграция `004` |
| Справочник штрихкодов | `barcode_reference`, миграция `005`, `app/tools/load_barcode_reference.py` |
| Канонизация по match_pair | `app/analytics/canonical_sync.py` |
| TF‑IDF + greedy one-to-one | `app/ml/tfidf_pairs.py` |
| Модель и константы `match_kind` / `match_status` | `app/database.py` |
| Миграция 002 | `alembic/versions/002_match_governance.py` |
| Метрики полноты / exact пересечений | `app/quality/coverage.py` |
| UI ревью | `app/web/main.py` (`/matches/.../status`), шаблоны `matches.html`, `product_detail.html` |
| Миграция 003, норм. слой | `alembic/versions/003_price_intelligence_layer.py` |
| Matching exact-first, fuzzy review | `app/ml/matching.py` |
| KPI / рынок | `app/analytics/price_intelligence.py` |
| Аудит URL прайсов | `python -m app.tools.source_audit` → `source_audit.csv` |
