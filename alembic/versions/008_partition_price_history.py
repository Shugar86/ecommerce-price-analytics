"""Партиционирование таблицы price_history по диапазону дат (RANGE).

Revision ID: 008_partition_price_history
Revises: 007_owwa_listings
Create Date: 2026-05-15

Обоснование (подраздел 2.2.10 отчёта):
    Таблица price_history растёт пропорционально числу товаров и частоте
    опросов. При 50 000 активных позиций и ежечасовом обновлении за год
    накапливается порядка 400 млн строк. Запрос истории за конкретный месяц
    без партиционирования вынуждает PostgreSQL просматривать всю таблицу
    (Seq Scan) даже при наличии индекса по collected_at.

    Решение — декларативное секционирование по диапазону (PARTITION BY RANGE)
    по полю collected_at с гранулярностью «один раздел = один месяц». При
    запросе данных за конкретный период PostgreSQL выбирает только те разделы,
    чьи границы перекрываются с условием WHERE — Partition Pruning.

Стратегия безопасной миграции:
    1. Создать новую партиционированную таблицу price_history_new.
    2. Перенести данные через INSERT … SELECT.
    3. Переименовать таблицы (атомарная операция в рамках транзакции).
    4. downgrade() — обратный перенос данных в обычную таблицу.

Предварительный шаг (вне миграции):
    Перед запуском выполнить резервное копирование:
        pg_dump -t price_history prices_db > price_history_backup.sql
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_partition_price_history"
down_revision: Union[str, None] = "007_owwa_listings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Диапазон партиций: 2024-01 … 2026-12 плюс защитная партиция DEFAULT
_PARTITIONS = [
    ("price_history_2024_01", "2024-01-01", "2024-02-01"),
    ("price_history_2024_02", "2024-02-01", "2024-03-01"),
    ("price_history_2024_03", "2024-03-01", "2024-04-01"),
    ("price_history_2024_04", "2024-04-01", "2024-05-01"),
    ("price_history_2024_05", "2024-05-01", "2024-06-01"),
    ("price_history_2024_06", "2024-06-01", "2024-07-01"),
    ("price_history_2024_07", "2024-07-01", "2024-08-01"),
    ("price_history_2024_08", "2024-08-01", "2024-09-01"),
    ("price_history_2024_09", "2024-09-01", "2024-10-01"),
    ("price_history_2024_10", "2024-10-01", "2024-11-01"),
    ("price_history_2024_11", "2024-11-01", "2024-12-01"),
    ("price_history_2024_12", "2024-12-01", "2025-01-01"),
    ("price_history_2025_01", "2025-01-01", "2025-02-01"),
    ("price_history_2025_02", "2025-02-01", "2025-03-01"),
    ("price_history_2025_03", "2025-03-01", "2025-04-01"),
    ("price_history_2025_04", "2025-04-01", "2025-05-01"),
    ("price_history_2025_05", "2025-05-01", "2025-06-01"),
    ("price_history_2025_06", "2025-06-01", "2025-07-01"),
    ("price_history_2025_07", "2025-07-01", "2025-08-01"),
    ("price_history_2025_08", "2025-08-01", "2025-09-01"),
    ("price_history_2025_09", "2025-09-01", "2025-10-01"),
    ("price_history_2025_10", "2025-10-01", "2025-11-01"),
    ("price_history_2025_11", "2025-11-01", "2025-12-01"),
    ("price_history_2025_12", "2025-12-01", "2026-01-01"),
    ("price_history_2026_01", "2026-01-01", "2026-02-01"),
    ("price_history_2026_02", "2026-02-01", "2026-03-01"),
    ("price_history_2026_03", "2026-03-01", "2026-04-01"),
    ("price_history_2026_04", "2026-04-01", "2026-05-01"),
    ("price_history_2026_05", "2026-05-01", "2026-06-01"),
    ("price_history_2026_06", "2026-06-01", "2026-07-01"),
    ("price_history_2026_07", "2026-07-01", "2026-08-01"),
    ("price_history_2026_08", "2026-08-01", "2026-09-01"),
    ("price_history_2026_09", "2026-09-01", "2026-10-01"),
    ("price_history_2026_10", "2026-10-01", "2026-11-01"),
    ("price_history_2026_11", "2026-11-01", "2026-12-01"),
    ("price_history_2026_12", "2026-12-01", "2027-01-01"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Шаг 1: создать новую партиционированную таблицу
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS price_history_new (
            id          SERIAL,
            product_id  INTEGER NOT NULL,
            price_in_rub DOUBLE PRECISION NOT NULL,
            source_shop VARCHAR(100) NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            collected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, collected_at)
        ) PARTITION BY RANGE (collected_at)
    """))

    # Шаг 2: создать месячные разделы
    for name, start, end_ in _PARTITIONS:
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS {name}
            PARTITION OF price_history_new
            FOR VALUES FROM ('{start}') TO ('{end_}')
        """))

    # Шаг 3: раздел-catch-all для данных вне диапазона
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS price_history_default
        PARTITION OF price_history_new DEFAULT
    """))

    # Шаг 4: FK и индексы на партиционированной таблице
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_price_history_new_product_id
        ON price_history_new (product_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_price_history_new_collected_at
        ON price_history_new (collected_at)
    """))

    # Шаг 5: перенос данных
    conn.execute(sa.text("""
        INSERT INTO price_history_new
            (id, product_id, price_in_rub, source_shop, external_id, collected_at)
        SELECT id, product_id, price_in_rub, source_shop, external_id, collected_at
        FROM price_history
    """))

    # Шаг 6: замена таблицы (атомарно внутри транзакции)
    conn.execute(sa.text("ALTER TABLE price_history RENAME TO price_history_old"))
    conn.execute(sa.text("ALTER TABLE price_history_new RENAME TO price_history"))

    # Шаг 7: добавить внешний ключ на партиционированной таблице
    # (добавляем на уровне отдельного выражения после rename)
    conn.execute(sa.text("""
        ALTER TABLE price_history
        ADD CONSTRAINT fk_price_history_product_id
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    """))

    # Шаг 8: удалить исходную таблицу
    conn.execute(sa.text("DROP TABLE price_history_old"))


def downgrade() -> None:
    conn = op.get_bind()

    # Обратная операция: создать обычную таблицу, перенести данные
    conn.execute(sa.text("""
        CREATE TABLE price_history_plain (
            id          SERIAL PRIMARY KEY,
            product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            price_in_rub DOUBLE PRECISION NOT NULL,
            source_shop VARCHAR(100) NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            collected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text("""
        INSERT INTO price_history_plain
        SELECT id, product_id, price_in_rub, source_shop, external_id, collected_at
        FROM price_history
    """))
    conn.execute(sa.text("ALTER TABLE price_history RENAME TO price_history_partitioned"))
    conn.execute(sa.text("ALTER TABLE price_history_plain RENAME TO price_history"))
    conn.execute(sa.text("DROP TABLE price_history_partitioned CASCADE"))
