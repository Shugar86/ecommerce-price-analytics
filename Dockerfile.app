# Используем официальный Python образ
FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей для psycopg2 и lxml
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование файла зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения и миграций
COPY app/ /app/app/
COPY tools/ /app/tools/
COPY alembic.ini /app/alembic.ini
COPY alembic/ /app/alembic/

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# По умолчанию запускаем bash (команда переопределяется в docker-compose)
CMD ["/bin/bash"]

