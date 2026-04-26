# Микросервисное приложение сбора и визуального анализа цен (e-commerce)

Проект подходит для **ВКР / отчёта по практике**: микросервисная архитектура (Docker), **веб-приложение аналитика** (основной интерфейс), **сборщик** с нормализованным слоем `normalized_offers` и **price intelligence** (рынок, индекс цены, floor-маржа), **воркер аналитики** (аномалии цен, **кандидаты** наименований по TF‑IDF EKF↔TDM, простой прогноз), Telegram-бот (дополнительный канал).

**Сопоставление товаров между магазинами** в репозитории реализовано как **подсказки по сходству названий** и **точные пересечения ключей** (дашборд: полнота полей и overlap по `barcode` / `vendor_code` / `name_norm`), с возможностью **подтвердить или отклонить** кандидат в веб-интерфейсе. Это **не** система гарантированного глобального сопоставления каталогов; см. **[docs/PRODUCT_SCOPE.md](docs/PRODUCT_SCOPE.md)**.

## Быстрый старт

### 1. Токен Telegram-бота (опционально, для `bot`)

Telegram → @BotFather → `/newbot` → скопируйте токен.

### 2. Переменные окружения

Создайте `.env` в корне (см. **[env.example](env.example)**):

```env
POSTGRES_USER=courseuser
POSTGRES_PASSWORD=coursepass
POSTGRES_DB=prices_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

BOT_TOKEN=your_token_here_from_botfather

# Демо-точки истории цен для графиков (1/0); воркер аналитики
SEED_DEMO_HISTORY=1
AI_WORKER_INTERVAL_SEC=300
# Порог TF‑IDF EKF↔TDM (кандидаты, см. docs/PRODUCT_SCOPE.md); по умолчанию 0.45
# AI_MATCH_MIN_SCORE=0.45
# Источник, считающийся «нашим» в KPI market position (норм. слой)
# OUR_PRICING_SOURCE=EKF YML
# FakeStore (демо) выключен по умолчанию; включение: ENABLE_FAKESTORE=1
# Доп. переменные: [env.example](env.example) (SHOP_ITEM_LIMIT, AI_MATCH_LIMIT_PER_SHOP, …)
```

После обновления кода с миграциями схема БД подтягивается при старте (`init_db` → Alembic). **003** (`alembic/versions/003_price_intelligence_layer.py`) добавляет `normalized_offers`, `canonical_products`, `source_health`. **002** — поля `match_kind` / `match_status` в `product_matches`.

### 3. Запуск

```bash
docker compose up -d --build
```

Переменные из `.env` для ETL и KPI, если они заданы, подставляются в compose и передаются в сервисы: у **collector** — `SHOP_ITEM_LIMIT`, `ENABLE_FAKESTORE`, таймауты Complect-Service (`COMPLECT_SERVICE_*`), Syperopt, EKF, TDM, опционально `BARCODE_REFERENCE_AUTO_LOAD`, `ENABLE_OWWA`; API **barcodes-catalog.ru** в основной цикл collector **не входит** (Cloudflare). У **web** и **ai_worker** — `OUR_PRICING_SOURCE`, `OUR_PRICING_SOURCE_PRIORITY`, `AI_MATCH_SOURCE_PAIRS` и др. Таблица `source_health` в UI `/sources` показывает `last_error` и длительность загрузки. Загрузка штрихкодов Catalog.app: `python -m app.tools.fetch_barcode_reference_catalog` или `app.collectors.barcode_reference_loader` (см. `env.example`). Локальный `docker-compose.override.yml` может переопределить порты (например **8010** вместо 8000).

В **`normalized_offers` / `source_health`** попадают: **EKF YML**, **TDM Electric**, **Syperopt XLSX**, прайсы **Комплект-Сервис** (имена вида `EKF (Комплект-Сервис)`, `IEK (Комплект-Сервис)`, `Schneider Electric (КС)`, `Legrand (Комплект-Сервис)`, `WAGO (Комплект-Сервис)`, `Full Price (Комплект-Сервис)` — агрегированный full пропускается, если успешно загружены все пять брендовых XLS), **TBM Market** и **GalaCentre** (YML). См. раздел **«Источники данных»** ниже с URL.

По умолчанию **PostgreSQL и Adminer не проброшены на хост** (только внутри сети Docker). Чтобы открыть порты `5432` и `8080` для локальной отладки:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

**Опционально — защита веб-интерфейса:** если в `.env` задать **оба** параметра `WEB_BASIC_AUTH_USER` и `WEB_BASIC_AUTH_PASSWORD`, дашборд и CSV потребуют HTTP Basic Auth (эндпоинты `/health` и `/ready` остаются без пароля).

Сервисы:

| Сервис     | Назначение |
|------------|------------|
| `db`       | PostgreSQL |
| `adminer`  | Веб-админка БД (порт 8080 только с `docker-compose.dev.yml`) |
| `collector`| ETL, сбор прайсов |
| `web`      | **Аналитика** → http://localhost:8000 |
| `ai_worker`| Аномалии, fuzzy-кандидаты по **normalized_offers** (EKF YML↔TDM), опционально legacy TF‑IDF по `products`, прогнозы |
| `bot`      | Telegram-бот |

### 4. Проверка

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
docker compose logs -f collector
docker compose logs -f ai_worker
```

В браузере: **http://localhost:8000** — **«Сегодня»** (сигналы KPI, источники, ревью), **рынок** (`/market`), **источники** (`/sources`), товары, **алерты** (`/alerts`, бывш. аномалии), сопоставления, выгрузки CSV.

**Пакет для защиты (полный ETL, цифры, скриншоты):** после цикла `collector` запустите [`tools/etl_defense_report.py`](tools/etl_defense_report.py) — срез `source_health`, агрегаты по `normalized_offers` / канонам / `normalized_offer_matches` и готовый список URL веб-UI. Команды, ожидание по логу и порт **8010** с override — в **[COMMANDS.md](COMMANDS.md)** (раздел «Защита»).

**Аудит прайс-файлов** (покрытие price/vendor_code/barcode, `usable_score`) в CSV:

```bash
.venv/bin/python -m app.tools.source_audit
# → source_audit.csv в текущем каталоге; путь: SOURCE_AUDIT_OUT=путь/к/файлу
```

### 5. Тесты (локально)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests/ -q
```

## Структура проекта (runtime)

```
├── app/
│   ├── database.py          # Модели БД (+ история, аномалии, матчи, прогноз)
│   ├── collector.py         # ETL
│   ├── price_history_util.py
│   ├── matching/            # нормализация имён, эвристики сравнения (бот / ETL / отчёты)
│   ├── quality/             # полнота полей + exact-пересечения для дашборда
│   ├── services/            # общие read-запросы (например SQL для бота)
│   ├── bot.py               # Telegram
│   ├── ai_worker.py         # аномалии, кандидаты TF‑IDF, прогноз
│   ├── ml/                  # Аномалии, TF-IDF
│   └── web/                 # FastAPI + Jinja2 + шаблоны (+ web/services: агрегаты дашборда)
├── tests/                   # pytest
├── docs/                    # заметки к рефакторингу
├── alembic/                 # миграции схемы (патчи индексов / колонок)
├── docker-compose.yml
└── docker-compose.dev.yml   # опционально: порты db + adminer на хост
```

**Тексты ВКР / пояснительные записки** (`VKR_AND_PRACTICE_REPORT.md`, `README_REPORT.md`, `INDEX.md` и т.д.) остаются в репо как документация; **крупные бинарники** (XLS, PDF, изображения, снимки прайсов) в индекс git не попадают — см. `.gitignore` и [docs/REFACTOR_NOTES.md](docs/REFACTOR_NOTES.md). Храните такие файлы локально, в LFS или в релизах.

## Источники данных

Активные коллекторы и публичные URL (константы в основном в `app/collector.py`, `app/collectors/complect_service.py`, `app/collectors/syperopt.py`):

| Источник | Описание | URL |
|----------|----------|-----|
| ЦБ РФ | Курс USD (XML) | `http://www.cbr.ru/scripts/XML_daily.asp` |
| TBM Market | YML | `https://www.tbmmarket.ru/tbmmarket/service/yandex-market.xml` |
| GalaCentre | YML | `https://www.galacentre.ru/download/yml/yml.xml` |
| EKF | YML | `https://export-xml.storage.yandexcloud.net/products.yml` |
| TDM Electric | XLS | `https://tdme.ru/download/priceTDM.xls` |
| Complect-Service EKF | XLS | `https://www.complect-service.ru/prices/ekf.xls` |
| Complect-Service IEK | XLS | `https://www.complect-service.ru/prices/ieknew.xls` |
| Complect-Service Schneider | XLS | `https://www.complect-service.ru/prices/schneider.xls` |
| Complect-Service Legrand | XLS | `https://www.complect-service.ru/prices/legrand.xls` |
| Complect-Service WAGO | XLS | `https://www.complect-service.ru/prices/wago.xls` |
| Complect-Service Full | XLS | `https://www.complect-service.ru/prices/fullpricecp.xls` (пропуск при успешных пяти брендах) |
| Syperopt | XLSX | `http://www.syperopt.ru/price_wago_abb_legrand_iek_495t5890043_syperopt_ru.xlsx` |
| FakeStore | JSON | `https://fakestoreapi.com/products` (только при `ENABLE_FAKESTORE=1`) |

Справочник штрихкодов (Tier B): ZIP Catalog.app `https://catalog.app/public-opportunities/download-public-file?fileName=barcodes_csv.zip` — загрузка вручную или `BARCODE_REFERENCE_AUTO_LOAD=true` при пустой таблице.

### Имена источников: `products` vs normalized layer

В legacy-таблице `products` источник EKF хранится как **`EKF`**. В нормализованном слое (`normalized_offers`, KPI, `/market`) тот же фид называется **`EKF YML`** (см. `OUR_PRICING_SOURCE`, по умолчанию `EKF YML`). Воркер сопоставления офферов использует имена нормализованного слоя (`AI_MATCH_NORMALIZED_LEFT` / `RIGHT`).

## Документация

- **[docs/PRODUCT_SCOPE.md](docs/PRODUCT_SCOPE.md)** — **объём продукта** по сопоставлению: кандидаты vs exact-ключи, ревью, формулировки для тезисов/ВКР.
- **[VKR_AND_PRACTICE_REPORT.md](VKR_AND_PRACTICE_REPORT.md)** — структура ВКР и отчёта по практике (главы 1–3).
- **[README_REPORT.md](README_REPORT.md)** — пояснительная записка с диаграммами (актуализируйте под веб/ИИ при сдаче).
- **[docs/REFACTOR_NOTES.md](docs/REFACTOR_NOTES.md)** — изменения в структуре кода и гигиене репозитория.

## Остановка

```bash
docker compose down      # контейнеры, volume БД сохраняется
docker compose down -v   # полная очистка данных
```

---

**Направление:** 09.03.03 «Прикладная информатика»
