# Демо-снимок данных для ВКР (воспроизводимые слайды)

Цель — **демонстрация**, а не промышленный SLA: один раз зафиксировать экспорт из БД и офлайн-сгенерированные PNG, чтобы перед защитой графики не «уплыли».

## Роли источников

| Источник | Роль для ВКР |
|----------|----------------|
| EKF YML, TDM, Комплект, Syperopt, TBM и др. | Основная линия **price intelligence**, реальная электро/ритейл номенклатура. |
| **CARRETA** (`ENABLE_CARRETA=1`) | Крупный **региональный** открытый CSV (РФ): объём строк, различие опт vs розница по **одним и тем же кодам**. |
| Open Food Facts | Каталог/штрихкоды (**не** источник цен). |

## Шаги

1. **`ENABLE_CARRETA=1`** в `.env`/compose и цикл **`collector`** до успеха в `source_health` для источников `carreta_nsk_*`.

2. **Экспорт снимка** (каталог `artifacts/` по умолчанию в `.gitignore`):

   Из корня репозитория на хосте (нужны `POSTGRES_*` и доступ к той же БД, что и у collector):

   ```bash
   python tools/export_demo_snapshot.py --out-dir artifacts/demo --per-source-limit 12000
   ```

   Либо из образа collector (те же ограничения по `PYTHONPATH` и правам на `artifacts/`, см. ниже):

   ```bash
   docker compose run --rm -w /app -e PYTHONPATH=/app -v "$(pwd)/artifacts:/app/artifacts" \
     -e DEFENSE_SNAPSHOT_SOURCES=carreta_nsk_opt,carreta_nsk_retail,carreta_nsk_stock \
     collector python tools/export_demo_snapshot.py --out-dir /app/artifacts/demo --per-source-limit 12000
   ```

   Файлы: `manifest.json` (метаданные, счётчики, воронка), `offers.csv` (выборка `normalized_offers`).

   Список источников задаётся **`DEFENSE_SNAPSHOT_SOURCES`** через запятую; по умолчанию экспортируются все три потока CARRETA из `CARRETA_FEEDS`.

3. **Графики**:

   ```bash
   # в образе collector: задайте PYTHONPATH и примонтируйте каталог artifacts
   docker compose run --rm -w /app -e PYTHONPATH=/app -v "$(pwd)/artifacts:/app/artifacts" \
     collector python tools/build_defense_visuals.py \
     --demo-dir /app/artifacts/demo --out-dir /app/artifacts/defense
   ```

   Выход: `source_coverage.png`, `demo_funnel.png`, `match_score_distribution.png`, `price_gap_by_source.png`, `top_matches.csv`.

   Если на хосте `Permission denied`, расширьте права на `artifacts/` (контейнер пишет от непривилегированного пользователя).

## Сопоставление «опт ↔ розница»

Дефолтная пара источников в `app/matching/source_pairs.py`: **`carreta_nsk_opt`** | **`carreta_nsk_retail`** — одинаковые `vendor_code`, разумные человекочитаемые названия для слайдов о расхождении цен.

## Нормализация названий

Модуль `app/ml/name_normalization.py` применяется в `match_pair` (fuzzy) и в предфильтре `ai_worker` по пересечению токенов — **объяснимые правила** для текста пояснительной записки.

## RU benchmark похожих товаров

Для акцента «российские реалии 2026 + сравнимые названия» есть отдельный контур:

```bash
docker compose run --rm -w /app -e PYTHONPATH=/app -v "$(pwd)/artifacts:/app/artifacts" \
  collector python tools/build_ru_matching_benchmark.py \
  --out-dir /app/artifacts/ru_benchmark \
  --per-source-limit 3000 \
  --max-positive-pairs 2500 \
  --max-negative-pairs 2500
```

Выход:

- `pairs.csv` — пары `match/non-match`;
- `metrics.csv` — precision/recall/F1 по порогам;
- `summary.json` — headline-цифры;
- `top_examples.csv` — красивые пары и сложные отрицательные примеры;
- `ru_match_score_distribution.png`, `ru_precision_recall.png`, `ru_f1_by_threshold.png`, `ru_confusion_matrix.png`.

Важно для честной формулировки: **label** строится по устойчивым ключам (`barcode` или `brand+vendor_code`), а **score** считается только по нормализованным названиям. То есть ключи используются как разметка, но не как «модель».
