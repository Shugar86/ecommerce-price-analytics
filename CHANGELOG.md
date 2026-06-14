# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

## [Unreleased]

### Added
- `README.md` — hero-секция, badge-линия, Mermaid-диаграмма архитектуры, развёрнутый быстрый старт, примеры API и экспорта.
- `AGENTS.md` — структурированный контракт: режим работы, вайб, стек, git workflow, Definition of Done, эскалация.
- `CONTRIBUTING.md` — чёткий процесс от форка до PR, именование веток, стиль кода, DoD.

### Changed
- Единые заголовки, бейджи и визуальная консистентность между документами.
- Уточнён стек: Python 3.11+, PostgreSQL 15, FastAPI, Docker Compose.

## [0.1.0] — 2026-06-14

### Added
- `feat: multi-pair fuzzy, local TDM XLS (Рыбинск), per-pair cap` — несколько пар источников для fuzzy-ревью, локальный прайс ТДМ Рыбинск, квоты на пару.
- `feat: Jaccard fuzzy matching, price-diff, EKF brand, worker blocking` — Jaccard-похожесть названий, анализ разницы цен, блокировки в воркере.
- `feat(etl): Complect-Service refactor, barcode_reference loader, pipeline tweaks` — рефакторинг коллектора Комплект-Сервис, загрузчик справочника штрихкодов.
- `ETL, защита, UI: норм. слой на дашборде, миграции, env, отчёт` — нормализованный слой в UI, миграции, env-переменные, отчёт для защиты.
- `feat(price-intelligence): canonical match_pair clusters, offer review queue, barcode_reference` — канонические кластеры, очередь ревью офферов, справочник штрихкодов.
- `feat: price intelligence — нормализованный слой, KPI и веб` — price intelligence, KPI, веб-дашборд.
- `feat: кандидаты сопоставления, ревью, метрики качества данных` — fuzzy-кандидаты, ручной ревью, метрики качества.
- `docs(vkr): expand section 2.2 — full academic text on collector ETL` — академическая документация по ETL.
- `refactor: three-pass architecture cleanup` — трёхпроходная архитектура.
- `refactor(collector): internal helpers for upsert, YML parse, TDM XLS` — внутренние хелперы ETL.
- `refactor: matching module, repo hygiene, bot/web service helpers` — модуль сопоставления, гигиена репозитория.
- `Initial commit: e-commerce price analytics (ETL, FastAPI, Docker, ML worker)` — базовый каркас: ETL, FastAPI, Docker, ML-воркер.

### Notes
- Версия `0.1.0` условная: проект развивается без тегов, поэтому дата соответствует моменту документирования.
