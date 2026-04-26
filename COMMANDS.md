# COMMANDS - Полезные команды для работы с проектом

## 🚀 Запуск и остановка

## 🪟 Windows (PowerShell) — запуск одной командой

В корне проекта есть скрипты `run.ps1` и `run.cmd`.

```powershell
# Первый запуск (сборка + старт)
.\run.ps1 up -Build

# Обычный запуск
.\run.ps1 up

# Статус
.\run.ps1 ps

# Логи
.\run.ps1 logs -Follow
.\run.ps1 logs -Service bot -Follow

# Остановка
.\run.ps1 stop
.\run.ps1 down
```

### Первый запуск системы
```bash
# Сборка и запуск всех контейнеров
docker-compose up -d --build
```

### Обычный запуск (после первого раза)
```bash
docker-compose up -d
```

### Остановка без удаления данных
```bash
docker-compose stop
```

### Остановка с удалением контейнеров (данные БД сохранятся)
```bash
docker-compose down
```

### Полная очистка (включая данные БД) ⚠️
```bash
docker-compose down -v
```

---

## 📊 Мониторинг и логи

### Статус всех контейнеров
```bash
docker-compose ps
```

### Логи всех сервисов
```bash
docker-compose logs
```

### Логи с отслеживанием (real-time)
```bash
# Все сервисы
docker-compose logs -f

# Только collector
docker-compose logs -f collector

# Только bot
docker-compose logs -f bot

# Только БД
docker-compose logs -f db
```

### Последние N строк логов
```bash
# Последние 50 строк
docker-compose logs --tail=50 collector

# Последние 100 строк всех сервисов
docker-compose logs --tail=100
```

---

## 🔄 Перезапуск сервисов

### Перезапустить конкретный сервис
```bash
docker-compose restart collector
docker-compose restart bot
docker-compose restart db
```

### Перезапустить все сервисы
```bash
docker-compose restart
```

### Пересобрать и перезапустить (после изменения кода)
```bash
docker-compose up -d --build collector bot
```

---

## 🐛 Отладка

### Войти в контейнер
```bash
# Collector
docker exec -it prices_collector bash

# Bot
docker exec -it prices_bot bash

# PostgreSQL
docker exec -it prices_db bash
```

### Выполнить команду в контейнере
```bash
# Проверить Python версию
docker exec prices_collector python --version

# Запустить скрипт проверки
docker exec prices_collector python check_system.py

# Посмотреть переменные окружения
docker exec prices_collector env | grep POSTGRES
```

### Просмотреть процессы внутри контейнера
```bash
docker exec prices_collector ps aux
```

---

## 🗄️ Работа с базой данных

### Подключиться к PostgreSQL через psql
```bash
docker exec -it prices_db psql -U courseuser -d prices_db
```

### SQL-команды (внутри psql)
```sql
-- Список таблиц
\dt

-- Структура таблицы
\d products
\d exchange_rates

-- Количество товаров
SELECT COUNT(*) FROM products;

-- Товары по источникам
SELECT source_shop, COUNT(*), AVG(price_in_rub) 
FROM products 
GROUP BY source_shop;

-- Последние 10 товаров
SELECT name, price_in_rub, source_shop 
FROM products 
ORDER BY updated_at DESC 
LIMIT 10;

-- Текущий курс USD
SELECT * FROM exchange_rates WHERE currency_code = 'USD';

-- Выход из psql
\q
```

### Резервное копирование БД
```bash
# Создать дамп
docker exec prices_db pg_dump -U courseuser prices_db > backup.sql

# Восстановить из дампа
cat backup.sql | docker exec -i prices_db psql -U courseuser -d prices_db
```

---

## 🌐 Веб-интерфейсы

### Adminer (управление БД)
```
URL: http://localhost:8080

Параметры подключения:
- Система: PostgreSQL
- Сервер: db
- Пользователь: courseuser
- Пароль: coursepass
- База данных: prices_db
```

---

## 🔍 Проверка и тестирование

### Автоматическая проверка системы
```bash
python check_system.py
```

### Проверка подключения к БД
```bash
docker exec prices_collector python -c "from app.database import get_engine; engine = get_engine(); print('✅ DB OK')"
```

### Ручной запуск сборщика данных (разово)
```bash
docker exec prices_collector python -m app.collector
```

### Проверка версий зависимостей
```bash
docker exec prices_collector pip list
```

---

## 🧹 Очистка и обслуживание

### Удалить неиспользуемые образы Docker
```bash
docker image prune -a
```

### Удалить неиспользуемые volumes
```bash
docker volume prune
```

### Посмотреть размер занимаемого места
```bash
docker system df
```

### Полная очистка Docker (осторожно!)
```bash
docker system prune -a --volumes
```

---

## 📦 Работа с зависимостями

### Обновить зависимости в контейнере
```bash
# Добавить новую библиотеку в requirements.txt, затем:
docker-compose build collector bot
docker-compose up -d
```

### Установить зависимости локально (для разработки)
```bash
pip install -r requirements.txt
```

---

## 🔐 Безопасность

### Изменить пароли БД
```bash
# 1. Остановить систему
docker-compose down -v

# 2. Изменить пароли в .env

# 3. Запустить заново
docker-compose up -d
```

### Сгенерировать новый токен бота
```
1. Открыть Telegram → @BotFather
2. Отправить /revoke
3. Выбрать бота
4. Отправить /token
5. Обновить BOT_TOKEN в .env
6. docker-compose restart bot
```

---

## 📈 Производительность

### Мониторинг ресурсов контейнеров
```bash
# Real-time статистика
docker stats

# Только для нашего проекта
docker stats prices_db prices_collector prices_bot
```

### Ограничить память контейнера
Добавить в `docker-compose.yml`:
```yaml
collector:
  deploy:
    resources:
      limits:
        memory: 512M
```

---

## 🛠️ Разработка

### Автоматическая перезагрузка при изменении кода
Добавить в `docker-compose.yml`:
```yaml
collector:
  volumes:
    - ./app:/app/app
  command: sh -c "while true; do python -m app.collector; sleep 5; done"
```

### Запуск линтера (локально)
```bash
# Установить
pip install pylint black

# Проверить код
pylint app/

# Отформатировать код
black app/
```

---

## 📤 Экспорт данных

### Экспорт товаров в CSV
```bash
docker exec prices_db psql -U courseuser -d prices_db -c "\COPY products TO '/tmp/products.csv' CSV HEADER"
docker cp prices_db:/tmp/products.csv ./products.csv
```

### Экспорт в JSON (через Python)
```python
# В контейнере collector
python -c "
from app.database import *
import json
engine = get_engine()
session = get_session(engine)
products = session.query(Product).all()
data = [{'name': p.name, 'price': p.price_in_rub} for p in products]
print(json.dumps(data, ensure_ascii=False, indent=2))
" > products.json
```

---

## 🎓 Полезные команды для демонстрации

### Быстрая проверка перед защитой
```bash
# 1. Статус
docker-compose ps

# 2. Короткие логи
docker-compose logs --tail=20 collector
docker-compose logs --tail=20 bot

# 3. Проверка данных
docker exec prices_db psql -U courseuser -d prices_db -c "SELECT source_shop, COUNT(*) FROM products GROUP BY source_shop;"

# 4. Курс валют
docker exec prices_db psql -U courseuser -d prices_db -c "SELECT * FROM exchange_rates;"
```

### Одной командой: остановить, очистить, запустить заново
```bash
docker-compose down -v && docker-compose up -d --build && docker-compose logs -f
```

---

## 📞 Решение проблем

### Контейнер не запускается
```bash
# Посмотреть детальные логи
docker-compose logs <service_name>

# Проверить конфигурацию
docker-compose config

# Пересоздать контейнер
docker-compose up -d --force-recreate <service_name>
```

### Порт уже занят
```bash
# Windows: найти процесс на порту 8080
netstat -ano | findstr :8080

# Убить процесс (замените PID)
taskkill /PID <PID> /F

# Или изменить порт в docker-compose.yml
```

### База данных заблокирована
```bash
# Посмотреть активные подключения
docker exec prices_db psql -U courseuser -d prices_db -c "SELECT * FROM pg_stat_activity;"

# Убить зависшие запросы (если есть)
docker-compose restart db
```

---

## 🎯 Алиасы для удобства (опционально)

Добавьте в `.bashrc` или `.zshrc` (Linux/Mac):
```bash
alias dcu='docker-compose up -d'
alias dcd='docker-compose down'
alias dcl='docker-compose logs -f'
alias dcp='docker-compose ps'
alias dcr='docker-compose restart'

# Использование:
# dcu      - запустить
# dcl bot  - логи бота
# dcp      - статус
```

Для Windows PowerShell добавьте в профиль:
```powershell
function dcu { docker-compose up -d }
function dcd { docker-compose down }
function dcl { docker-compose logs -f $args }
```

---

**Совет:** Добавьте этот файл в закладки — сэкономит много времени при работе с проектом!

