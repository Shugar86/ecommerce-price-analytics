# Price Intelligence для B2B-прайсов

> Аналитика цен, которая не кричит, а показывает цифры: собирает прайсы, строит историю и помогает принимать решения на основе данных, а не интуиции.

Это микросервисное приложение для сбора и визуального анализа цен в электротехническом B2B-сегменте. Оно объединяет фиды поставщиков (EKF, TDM Electric, Комплект-Сервис, Syperopt и др.), нормализует офферы, считает рыночные KPI и даёт аналитику **кандидатов на сопоставление** для ручного ревью.

Проект готов к использованию в **ВКР / отчёте по практике**: полная Docker-сборка, веб-дашборд, Telegram-бот, тесты и инструменты для защиты.

## Что это решает

- **Сбор цен из десятков источников** — YML, XLS, XLSX, JSON и локальные файлы в единый нормализованный слой.
- **Контроль качества данных** — полнота полей, exact-пересечения по `barcode` / `vendor_code`, `source_health` с ошибками и длительностью загрузки.
- **Price intelligence** — медиана, индекс цены, эвристика себестоимости и floor-маржи, рекомендуемое действие.
- **Ассистированное сопоставление** — fuzzy-кандидаты (Jaccard / TF‑IDF) и LLM-второе мнение, которые аналитик подтверждает или отклоняет вручную.
- **Аномалии и прогноз** — воркер ищёт скачки цен, поддельные скидки и строит упрощённый линейный прогноз.

## Возможности

- Мультиисточниковый ETL с `docker compose up`.
- Нормализованный слой `normalized_offers` + канонические кластеры `canonical_products`.
- Веб-интерфейс аналитика: «Сегодня», рынок, источники, сопоставления, алерты.
- Telegram-бот для быстрых запросов.
- Alembic-миграции, pytest-тесты, CI-ready структура.
- Инструменты для защиты: отчёты, диаграммы, скриншоты, выгрузки.

## Быстрый старт

### 1. Переменные окружения

Скопируйте пример и настройте `.env`:

```bash
cp env.example .env
# отредактируйте .env в редакторе
```

Минимальный набор:

```env
POSTGRES_USER=courseuser
POSTGRES_PASSWORD=coursepass
POSTGRES_DB=prices_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Опционально: Telegram-бот
BOT_TOKEN=your_token_here_from_botfather

SEED_DEMO_HISTORY=1
AI_WORKER_INTERVAL_SEC=300
```

Полный список переменных и их смысл — в [`env.example`](./env.example) и [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md).

### 2. Запуск

```bash
docker compose up -d --build
```

Откройте дашборд: [http://localhost:8000](http://localhost:8000)

Для доступа к PostgreSQL и Adminer на хосте:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### 3. Проверка

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
docker compose logs -f collector
```

## Сервисы

| Сервис | Назначение |
|--------|------------|
| `db` | PostgreSQL |
| `adminer` | Веб-админка БД (только с `docker-compose.dev.yml`) |
| `collector` | ETL: сбор, нормализация и загрузка прайсов |
| `web` | FastAPI + Jinja2 дашборд → [http://localhost:8000](http://localhost:8000) |
| `ai_worker` | Аномалии, fuzzy-кандидаты, прогнозы |
| `bot` | Telegram-бот |

## Архитектура и стек

| Область | Технология |
|---------|------------|
| Язык | Python 3.12 |
| Веб | FastAPI, Jinja2, HTMX-like шаблоны |
| База данных | PostgreSQL 16, SQLAlchemy, Alembic |
| ML/аналитика | scikit-learn, pandas, numpy |
| Инфраструктура | Docker, Docker Compose, nginx |
| Тесты | pytest, coverage |
| Автоматизация | GitHub Actions (`.github/workflows`) |

## Структура проекта

```text
.
├── app/
│   ├── collector.py            # основной ETL-цикл
│   ├── ai_worker.py            # воркер аномалий и fuzzy-сопоставления
│   ├── bot.py                  # Telegram-бот
│   ├── database.py             # модели SQLAlchemy
│   ├── analytics/              # price intelligence, KPI, canonical sync
│   ├── collectors/             # парсеры конкретных источников
│   ├── matching/               # нормализация имён и текстовые эвристики
│   ├── ml/                     # TF-IDF, Jaccard, name normalization
│   ├── quality/                # метрики полноты и exact-пересечений
│   ├── services/               # общие read-запросы
│   └── web/                    # FastAPI + шаблоны
├── alembic/                    # миграции БД
├── tests/                      # pytest
├── tools/                      # скрипты защиты, диаграммы, отчёты
├── docs/                       # продуктовая и академическая документация
├── docker-compose.yml          # production-like запуск
├── docker-compose.dev.yml      # dev-порты db/adminer
├── env.example                 # шаблон переменных окружения
└── COMMANDS.md                 # шпаргалка по командам
```

## Источники данных

| Источник | Формат | URL |
|----------|--------|-----|
| ЦБ РФ | XML | `http://www.cbr.ru/scripts/XML_daily.asp` |
| EKF | YML | `https://export-xml.storage.yandexcloud.net/products.yml` |
| TDM Electric | XLS | `https://tdme.ru/download/priceTDM.xls` |
| Комплект-Сервис (бренды) | XLS | `https://www.complect-service.ru/prices/ekf.xls` и др. |
| Syperopt | XLSX | `http://www.syperopt.ru/price_wago_abb_legrand_iek_495t5890043_syperopt_ru.xlsx` |
| TBM Market | YML | `https://www.tbmmarket.ru/tbmmarket/service/yandex-market.xml` |
| GalaCentre | YML | `https://www.galacentre.ru/download/yml/yml.xml` |
| FakeStore | JSON | `https://fakestoreapi.com/products` (только при `ENABLE_FAKESTORE=1`) |

Справочник штрихкодов (Tier B): Catalog.app ZIP — см. `env.example`.

## Важное уточнение про сопоставление

Система **не** обещает полностью автоматическое объединение каталогов без ошибок. Она даёт:

1. **Exact-пересечения** по устойчивым ключам (`barcode`, `vendor_code`, `brand+артикул`).
2. **Fuzzy-кандидатов** по сходству наименований (Jaccard / TF‑IDF).
3. **Ручной ревью** в веб-интерфейсе: подтвердить или отклонить.

Подробнее — в [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md).

## Тесты

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests/ -q
```

## Документация

- [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md) — объём продукта и терминология.
- [`COMMANDS.md`](COMMANDS.md) — команды для запуска, отладки, защиты.
- [`ENV_SETUP.md`](ENV_SETUP.md) — как создать `.env` и получить токен бота.
- [`VKR_AND_PRACTICE_REPORT.md`](VKR_AND_PRACTICE_REPORT.md) — структура ВКР и отчёта по практике.
- [`CHANGELOG.md`](CHANGELOG.md) — история изменений.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — как участвовать.

## Лицензия

[MIT](./LICENSE) © Shugar86.

---

**Направление:** 09.03.03 «Прикладная информатика»
