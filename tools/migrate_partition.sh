#!/usr/bin/env bash
# Безопасный запуск миграции партиционирования price_history.
#
# Последовательность:
#   1. pg_dump — снимок таблицы price_history до миграции (резервная копия)
#   2. alembic upgrade 008_partition_price_history — сама миграция
#   3. Проверочный запрос — вывод структуры партиционированной таблицы
#
# Использование:
#   bash tools/migrate_partition.sh
#
# Переменные окружения (из .env):
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

set -euo pipefail

BACKUP_DIR="artifacts/pg_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/price_history_before_partition_${TIMESTAMP}.sql"

# Загрузка переменных окружения
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

PGHOST="${POSTGRES_HOST:-db}"
PGPORT="${POSTGRES_PORT:-5432}"
PGDB="${POSTGRES_DB:-prices_db}"
PGUSER="${POSTGRES_USER:-courseuser}"
export PGPASSWORD="${POSTGRES_PASSWORD:-coursepass}"

echo "=== [1/3] Резервное копирование price_history ==="
mkdir -p "${BACKUP_DIR}"
docker exec prices_db pg_dump \
    -h localhost \
    -U "${PGUSER}" \
    -d "${PGDB}" \
    -t price_history \
    --no-owner \
    --no-acl \
    > "${BACKUP_FILE}"
echo "    Backup saved: ${BACKUP_FILE} ($(wc -c < "${BACKUP_FILE}") bytes)"

echo ""
echo "=== [2/3] Запуск Alembic-миграции 008 ==="
docker exec prices_web alembic upgrade 008_partition_price_history

echo ""
echo "=== [3/3] Проверка: структура партиционированной таблицы ==="
docker exec prices_db psql \
    -U "${PGUSER}" \
    -d "${PGDB}" \
    -c "\d+ price_history"

echo ""
echo "=== Список разделов ==="
docker exec prices_db psql \
    -U "${PGUSER}" \
    -d "${PGDB}" \
    -c "SELECT tablename, pg_size_pretty(pg_total_relation_size(quote_ident(tablename))) AS size
        FROM pg_tables
        WHERE tablename LIKE 'price_history_%'
        ORDER BY tablename;"

echo ""
echo "=== EXPLAIN ANALYZE: запрос истории за май 2026 ==="
docker exec prices_db psql \
    -U "${PGUSER}" \
    -d "${PGDB}" \
    -c "EXPLAIN ANALYZE
        SELECT id, price_in_rub, collected_at
        FROM price_history
        WHERE collected_at BETWEEN '2026-05-01' AND '2026-06-01'
        LIMIT 100;"

echo ""
echo "Миграция завершена."
