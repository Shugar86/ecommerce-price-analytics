# FAQ - Часто задаваемые вопросы

## Установка и запуск

### ❓ Docker не установлен. Где его скачать?

**Для Windows:**
1. Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop
2. Установите и перезагрузите компьютер
3. Убедитесь, что Docker запущен (иконка в трее)

**Для Linux:**
```bash
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
```

### ❓ Как создать файл .env в Windows?

**Способ 1 (через Notepad):**
1. Откройте Блокнот
2. Вставьте содержимое из ENV_SETUP.md
3. Нажмите "Файл" → "Сохранить как"
4. Выберите "Все файлы" в типе файла
5. Введите имя: `.env` (с точкой!)
6. Сохраните в папку C:\Repo\

**Способ 2 (через PowerShell):**
```powershell
cd C:\Repo
Copy-Item env.example .env
notepad .env
```

### ❓ Команда docker-compose не найдена

**Решение:**
Используйте `docker compose` (через пробел) вместо `docker-compose`:

```bash
docker compose up -d
docker compose logs -f collector
docker compose down
```

### ❓ Ошибка: "port is already allocated"

**Причина:** Порт уже занят другим приложением.

**Решение:**
Измените порты в `docker-compose.yml`:

```yaml
adminer:
  ports:
    - "8081:8080"  # Изменили 8080 на 8081

db:
  ports:
    - "5433:5432"  # Изменили 5432 на 5433
```

## Работа с ботом

### ❓ Бот не отвечает в Telegram

**Проверьте:**

1. Правильность токена в `.env`:
```bash
# Посмотреть текущий токен (Windows PowerShell)
cat .env | Select-String "BOT_TOKEN"
```

2. Статус контейнера:
```bash
docker compose ps
docker compose logs bot
```

3. Бот должен быть запущен:
```
INFO - 🤖 Telegram-бот запущен и ожидает сообщений...
```

**Если бот все равно не работает:**
```bash
docker compose restart bot
```

### ❓ Бот отвечает, но говорит "данные не загружены"

**Причина:** Сборщик еще не выполнил первый цикл.

**Решение:**
Подождите 1-2 минуты. Проверьте логи:

```bash
docker compose logs collector
```

Должны быть строки:
```
INFO - ✅ Курс USD успешно сохранен в БД
INFO - ✅ Успешно сохранено X товаров от FakeStore
INFO - ✅ Успешно сохранено X товаров от TBM Market
```

### ❓ Команда /find ничего не находит

**Возможные причины:**

1. Данные еще не загружены (см. предыдущий вопрос)
2. Запрос слишком специфичный

**Попробуйте:**
```
/find phone
/find laptop
/find bag
/find shirt
```

## Проблемы с базой данных

### ❓ Ошибка: "could not translate host name 'db' to address"

**Причина:** Контейнер с БД не запущен или недоступен.

**Решение:**
```bash
# Проверить статус
docker compose ps

# Если db не запущен
docker compose up -d db

# Подождать 5 секунд и перезапустить другие сервисы
docker compose restart collector bot
```

### ❓ Как посмотреть содержимое БД?

**Способ 1 (через Adminer):**
1. Откройте http://localhost:8080
2. Введите:
   - Система: PostgreSQL
   - Сервер: `db`
   - Пользователь: `courseuser`
   - Пароль: `coursepass`
   - База данных: `prices_db`
3. Нажмите "Войти"

**Способ 2 (через командную строку):**
```bash
docker exec -it prices_db psql -U courseuser -d prices_db

# SQL-запросы:
SELECT * FROM exchange_rates;
SELECT COUNT(*) FROM products;
SELECT * FROM products LIMIT 10;
```

Для выхода из psql: `\q`

### ❓ Как очистить все данные и начать заново?

**ВНИМАНИЕ:** Это удалит все данные!

```bash
# Остановить и удалить контейнеры + volumes
docker compose down -v

# Запустить заново
docker compose up -d
```

## Проблемы при сборе данных

### ❓ Ошибка: "❌ Ошибка при запросе к ЦБ РФ"

**Причина:** Нет доступа к интернету или сайт ЦБ РФ недоступен.

**Решение:**
1. Проверьте интернет-соединение
2. Попробуйте открыть http://www.cbr.ru/scripts/XML_daily.asp в браузере
3. Подождите и повторите попытку (сборщик автоматически попытается снова через час)

### ❓ Ошибка: "❌ Не найден курс USD в ответе ЦБ РФ"

**Причина:** Изменился формат XML от ЦБ РФ (редко) или проблема с кодировкой.

**Решение:**
1. Проверьте файл вручную: http://www.cbr.ru/scripts/XML_daily.asp
2. Убедитесь, что там есть элемент с `<CharCode>USD</CharCode>`
3. Если формат изменился, потребуется обновить парсер в `app/collector.py`

### ❓ Собирается только 20 товаров от TBM Market. Почему?

**Ответ:** Это сделано специально для демонстрации.

В `app/collector.py` есть константа:
```python
RUSSIAN_GOODS_LIMIT = 20
```

Можно изменить на большее значение (например, 100):
```python
RUSSIAN_GOODS_LIMIT = 100
```

После изменения:
```bash
docker compose restart collector
```

## Разработка и отладка

### ❓ Как изменить код без пересборки контейнера?

**Решение:** Используйте volume-монтирование.

Добавьте в `docker-compose.yml` для сервисов `collector` и `bot`:

```yaml
volumes:
  - ./app:/app/app
```

Теперь изменения в коде будут сразу видны (но нужен перезапуск контейнера):

```bash
docker compose restart collector
docker compose restart bot
```

### ❓ Как запустить код локально (без Docker)?

**Требования:**
- Python 3.11+
- PostgreSQL установлен и запущен

**Шаги:**

1. Установить зависимости:
```bash
pip install -r requirements.txt
```

2. Изменить `.env` (заменить `db` на `localhost`):
```env
POSTGRES_HOST=localhost
```

3. Запустить БД:
```bash
docker compose up -d db
```

4. Запустить сборщик:
```bash
python -m app.collector
```

5. В другом терминале запустить бота:
```bash
python -m app.bot
```

### ❓ Как посмотреть детальные логи?

**Добавьте в начало `app/collector.py` и `app/bot.py`:**

```python
logging.basicConfig(
    level=logging.DEBUG,  # Изменить INFO на DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

Пересоберите контейнеры:
```bash
docker compose up -d --build
```

## Презентация и защита

### ❓ Как подготовиться к демонстрации преподавателю?

**Чек-лист:**

1. ✅ Система запущена: `docker compose ps` (все "Up")
2. ✅ Данные загружены: `/stats` в боте показывает товары
3. ✅ Поиск работает: `/find phone` находит товары
4. ✅ Adminer открывается: http://localhost:8080
5. ✅ Логи чистые (нет критических ошибок): `docker compose logs`

**Сценарий демонстрации:**

1. Показать структуру проекта в редакторе кода
2. Показать `docker-compose.yml` и объяснить сервисы
3. Запустить `docker compose ps` — показать 4 контейнера
4. Открыть Telegram и продемонстрировать команды бота
5. Открыть Adminer и показать таблицы с данными
6. Показать диаграммы из README_REPORT.md

### ❓ Какие вопросы могут задать на защите?

**Типичные вопросы:**

1. **Почему выбрали эти источники данных?**
   → См. раздел 1 в README_REPORT.md

2. **Как работает потоковый парсинг XML?**
   → Объяснить `iterparse()` и очистку памяти

3. **Что будет при одновременной записи от разных процессов?**
   → PostgreSQL обеспечивает ACID, используем UPSERT

4. **Как система масштабируется?**
   → Легко добавить новые контейнеры collector для других источников

5. **Почему Telegram, а не веб-интерфейс?**
   → Простота реализации, кроссплатформенность, асинхронность

### ❓ Где взять скриншоты для документа?

**Рекомендуемые скриншоты:**

1. Telegram-бот: команды /start, /stats, /find
2. Adminer: таблицы products и exchange_rates
3. Docker Desktop: список запущенных контейнеров
4. VS Code: структура проекта
5. Терминал: логи `docker compose logs`

**Инструмент:** Windows Snipping Tool (Win+Shift+S)

## Контакты и поддержка

### ❓ Система не работает, что делать?

**Диагностика:**

1. Запустите скрипт проверки:
```bash
python check_system.py
```

2. Соберите логи:
```bash
docker compose logs > logs.txt
```

3. Проверьте каждый контейнер:
```bash
docker compose ps
docker compose logs db
docker compose logs collector
docker compose logs bot
```

4. Обратитесь к преподавателю с:
   - Точным текстом ошибки
   - Файлом logs.txt
   - Версией Docker: `docker --version`

---

**Дополнительные ресурсы:**

- README.md — Краткое руководство
- README_REPORT.md — Полная документация для записки
- ENV_SETUP.md — Настройка переменных окружения

**Версия FAQ:** 1.0 (Декабрь 2025)

