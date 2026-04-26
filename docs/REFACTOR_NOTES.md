# Примечания к рефакторингу

## Удалён `app/beauty_bot.py`

Файл был внешним прототипом (другой предметной области), нигде не импортировался и не входил в Docker или точки входа. Удалён для ясности границ проекта. При необходимости восстановите из истории git до коммита с рефакторингом.

## Сопоставление наименований

Логика нормализации `name_norm` и эвристик `/compare` вынесена в пакет `app/matching/`. ETL и бот используют один модуль, чтобы не расходилось поведение поиска.

**Честный объём продукта (кандидаты + exact-метрики, не «магичный matching»):** см. [PRODUCT_SCOPE.md](PRODUCT_SCOPE.md). Для `product_matches` добавлены `match_kind` / `match_status`; `app/quality/coverage.py` питает дашборд.

## Второй проход (консолидация)

- Публичные хелперы в `app.matching.text`: `jaccard_similarity_sets`, `transliterate_ru_to_latin`, `normalize_for_match_scoring` — переиспользуются в `overlap_report` и `tdm_ekf_report` (где уместно; regex модельных токенов в отчётах намеренно отличается от бота).
- `app.services.product_queries` — общие read-only SQL для бота (магазины+кол-во, поиск, сравнение), чтобы снизить дублирование в `bot.py`.
- `app.web.services` — агрегаты главной страницы дашборда вне route handler.

## Крупные и учебные файлы

Бинарные и дублирующиеся артефакты (XLS, PDF, копии отчётов, UML-экспорты) убраны из индекса git. Локальные копии могут оставаться у разработчика; в репозиторий их не коммитим — см. `.gitignore` и раздел в README.

## Статусы плана `price_intelligence_reframe` (Cursor) vs код

В артефакте `price_intelligence_reframe_3453728d.plan.md` (Cursor) в YAML у пунктов остаётся `pending`, при этом в репозитории уже есть: миграции 002–005, слой `normalized_offers` / `canonical_products` / `source_health`, `normalized_offer_matches`, `barcode_reference`, `app/ml/matching.py` (exact-first + fuzzy не для auto-actions), `app/analytics/price_intelligence.py`, `app/tools/source_audit.py`, адаптеры `app/collectors/complect_service.py`, `syperopt.py`, страницы `/` (сегодня), `/market`, `/sources`, редирект `/anomalies` → `/alerts`, README/PRODUCT_SCOPE, тесты (`test_matching_v2`, `test_kpi_engine`, `test_source_audit`, `test_price_intelligence_db`, `test_barcode_enrich`). Для проверки готовности ориентироваться на **код, pytest и миграции**, а не на frontmatter старого plan-файла.
