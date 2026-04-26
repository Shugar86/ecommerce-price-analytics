# Инструкция по созданию файла .env

Этот файл должен находиться в корне проекта и содержать секретные данные.

## Шаг 1: Создайте файл .env

В корне проекта (C:\Repo\) создайте файл с именем `.env` (с точкой в начале).

## Шаг 2: Скопируйте содержимое

Вставьте в файл следующее содержимое:

```
POSTGRES_USER=courseuser
POSTGRES_PASSWORD=coursepass
POSTGRES_DB=prices_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

BOT_TOKEN=your_token_here_from_botfather

# ИИ-воркер (аномалии, TF-IDF): интервал в секундах; демо-история цен для графиков
AI_WORKER_INTERVAL_SEC=300
SEED_DEMO_HISTORY=1
```

После запуска откройте веб-интерфейс аналитика: **http://localhost:8000** (сервис `web`).

## Шаг 3: Получите токен бота

1. Откройте Telegram
2. Найдите бота @BotFather
3. Отправьте команду /newbot
4. Следуйте инструкциям:
   - Введите имя бота (например: "Price Collector Bot")
   - Введите username бота (должен заканчиваться на "bot", например: "my_price_collector_bot")
5. Скопируйте полученный токен (выглядит примерно так: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)

## Шаг 4: Вставьте токен

Замените `your_token_here_from_botfather` на ваш реальный токен:

```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

## Готово!

Теперь можно запускать систему командой:

```bash
docker-compose up -d
```

## Важно!

- Файл .env НЕ должен попадать в git (он уже добавлен в .gitignore)
- Никогда не публикуйте токен бота в открытых источниках
- Если токен скомпрометирован, используйте команду /revoke в @BotFather

