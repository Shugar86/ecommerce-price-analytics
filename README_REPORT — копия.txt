# ПОЯСНИТЕЛЬНАЯ ЗАПИСКА К КУРСОВОМУ ПРОЕКТУ

**Тема:** «Разработка распределенной системы сбора и анализа данных о ценах товаров с торговых площадок»

**Дисциплина:** Распределенные вычисления  
**Направление подготовки:** 09.03.03 «Программная инженерия»

---

## СОДЕРЖАНИЕ

1. [Введение](#1-введение)
2. [Аналитическая часть](#2-аналитическая-часть)
   - 2.1. [Описание предметной области](#21-описание-предметной-области)
   - 2.2. [Обоснование применения распределенных вычислений](#22-обоснование-применения-распределенных-вычислений)
   - 2.3. [Теоретические основы распределенных систем](#23-теоретические-основы-распределенных-систем)
   - 2.4. [Концепции аппаратных и программных решений](#24-концепции-аппаратных-и-программных-решений)
3. [Практическое применение](#3-практическое-применение)
   - 3.1. [Анализ применяемых технологий](#31-анализ-применяемых-технологий)
   - 3.2. [Разработка программного приложения](#32-разработка-программного-приложения)
   - 3.3. [Описание контрольного примера](#33-описание-контрольного-примера)
4. [Диаграммы](#4-диаграммы)
   - 4.1. [ER-диаграмма (Entity-Relationship)](#41-er-диаграмма-entity-relationship)
   - 4.2. [Диаграмма классов (UML Class Diagram)](#42-диаграмма-классов-uml-class-diagram)
   - 4.3. [DFD — диаграмма потоков данных](#43-dfd--диаграмма-потоков-данных)
   - 4.4. [Диаграмма деятельности (Activity Diagram)](#44-диаграмма-деятельности-activity-diagram)
   - 4.5. [Диаграмма развертывания (Deployment Diagram)](#45-диаграмма-развертывания-deployment-diagram)
5. [Заключение](#5-заключение)
6. [Список использованных источников](#6-список-использованных-источников)

---

## 1. ВВЕДЕНИЕ

### Актуальность темы

В условиях современной цифровой экономики мониторинг цен на товары является критически важной задачей как для бизнеса, так и для потребителей. Разнообразие торговых площадок, различия в форматах представления данных и валютах создают потребность в автоматизированных системах сбора и анализа ценовой информации.

### Цель проекта

Разработка распределенной системы, обеспечивающей:
- Автоматический сбор данных о ценах с нескольких торговых площадок
- Приведение цен к единой валюте (рубли) с использованием актуальных курсов ЦБ РФ
- Хранение и индексирование данных в реляционной СУБД
- Предоставление пользовательского интерфейса через Telegram-бота

### Задачи проекта

1. Спроектировать архитектуру распределенной системы с микросервисным подходом
2. Реализовать ETL-процесс для сбора данных из различных источников (API, YML, XLS)
3. Разработать механизм конвертации валют с использованием API ЦБ РФ
4. Создать Telegram-бота для взаимодействия с пользователями
5. Обеспечить контейнеризацию и оркестрацию компонентов через Docker

### Практическая значимость

Разработанная система позволяет:
- Экономить время на ручном мониторинге цен
- Сравнивать цены между различными поставщиками (EKF ↔ TDM Electric)
- Получать актуальные данные через удобный мессенджер
- Масштабировать решение за счет контейнеризации

---

## 2. АНАЛИТИЧЕСКАЯ ЧАСТЬ

### 2.1. Описание предметной области

**Предметная область:** автоматизированный мониторинг и сравнительный анализ цен на товары электротехнической продукции с нескольких торговых площадок.

#### Основные понятия предметной области

| Понятие | Определение |
|---------|-------------|
| **Товар (Product)** | Единица каталога с атрибутами: название, цена, валюта, источник, штрихкод, артикул |
| **Источник данных (Source)** | Торговая площадка, предоставляющая каталог товаров (YML-фид, REST API, прайс-лист) |
| **Курс валюты (ExchangeRate)** | Отношение иностранной валюты к рублю по данным ЦБ РФ |
| **ETL-процесс** | Извлечение (Extract), преобразование (Transform), загрузка (Load) данных |
| **YML-фид** | Yandex Market Language — XML-формат для обмена товарными каталогами |

#### Процессы предметной области

1. **Сбор данных** — периодическое получение каталогов товаров из внешних источников
2. **Нормализация** — приведение данных к единому формату (валюта, кодировка, структура)
3. **Хранение** — сохранение нормализованных данных в реляционной БД
4. **Анализ** — поиск, фильтрация, сравнение цен между источниками
5. **Представление** — вывод результатов пользователю через Telegram-интерфейс

### 2.2. Обоснование применения распределенных вычислений

#### Почему распределенная архитектура?

| Требование | Решение через распределенность |
|------------|-------------------------------|
| **Независимость компонентов** | Сборщик данных и бот работают как отдельные сервисы |
| **Отказоустойчивость** | Падение одного сервиса не влияет на остальные |
| **Масштабируемость** | Возможность запуска нескольких экземпляров сборщика |
| **Разнородность источников** | Каждый источник обрабатывается изолированно |

#### Обоснование выбора источников данных

##### Почему YML и API, а не парсинг HTML?

| Критерий | HTML-парсинг | YML/API |
|----------|--------------|---------|
| **Стабильность** | Ломается при изменении верстки | Структурированный формат, редко меняется |
| **Легальность** | Серая зона (robots.txt, ToS) | Официально предоставляемые данные |
| **Производительность** | Требует рендеринга страниц | Прямой доступ к данным, потоковая обработка |
| **Полнота данных** | Только видимые на странице | Полный каталог с метаданными |
| **Поддержка** | Требует постоянной адаптации | Минимальная поддержка |

**Вывод:** Использование структурированных форматов (YML, JSON API) обеспечивает надежность, легальность и эффективность системы.

##### Выбранные источники

| Источник | Формат | URL | Товаров |
|----------|--------|-----|---------|
| ЦБ РФ | XML API | cbr.ru/scripts/XML_daily.asp | Курсы валют |
| FakeStore | JSON REST API | fakestoreapi.com/products | ~20 |
| TBM Market | YML Stream | tbmmarket.ru/.../yandex-market.xml | ~5800 |
| GalaCentre | YML Stream | galacentre.ru/download/yml/yml.xml | ~14000 |
| TDM Electric | XLS (Excel) | tdme.ru/download/priceTDM.xls | ~19000 |
| EKF | YML (YandexCloud) | export-xml.storage.yandexcloud.net/products.yml | ~20000 |

### 2.3. Теоретические основы распределенных систем

#### Определение распределенной системы

> **Распределенная система** — совокупность независимых компьютеров, представляющаяся пользователю единой системой (Э. Таненбаум).

#### Ключевые характеристики (по Таненбауму)

1. **Прозрачность** — скрытие распределенности от пользователя
2. **Открытость** — стандартные интерфейсы взаимодействия
3. **Масштабируемость** — способность расти без потери производительности
4. **Отказоустойчивость** — продолжение работы при сбоях компонентов

#### Архитектурные паттерны

| Паттерн | Применение в проекте |
|---------|---------------------|
| **Микросервисы** | Разделение на Collector, Bot, Database |
| **ETL** | Сборщик данных реализует полный цикл Extract-Transform-Load |
| **Message-driven** | Telegram API как асинхронный канал взаимодействия |
| **Shared Database** | Единая PostgreSQL для всех сервисов |

### 2.4. Концепции аппаратных и программных решений

#### Аппаратная архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Host (Linux/Windows)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Collector  │  │    Bot      │  │    PostgreSQL       │  │
│  │  Container  │  │  Container  │  │    Container        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┴─────────────────────┘             │
│                    Docker Network (bridge)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │        Внешние источники       │
              │  ЦБ РФ, YML-фиды, REST API    │
              └───────────────────────────────┘
```

#### Программный стек

| Компонент | Технология | Версия | Назначение |
|-----------|------------|--------|------------|
| Язык программирования | Python | 3.11+ | Основной язык разработки |
| СУБД | PostgreSQL | 15 | Хранение данных |
| ORM | SQLAlchemy | 2.0+ | Работа с БД |
| Telegram-фреймворк | aiogram | 3.x | Telegram Bot API |
| HTTP-клиент | requests | 2.31+ | Запросы к API |
| XML-парсер | lxml | 5.x | Потоковый парсинг YML |
| Контейнеризация | Docker | 24+ | Изоляция сервисов |
| Оркестрация | Docker Compose | 2.x | Управление контейнерами |

---

## 3. ПРАКТИЧЕСКОЕ ПРИМЕНЕНИЕ

### 3.1. Анализ применяемых технологий

#### Потоковый парсинг XML (lxml.iterparse)

**Проблема:** YML-фиды могут содержать сотни тысяч товаров (десятки мегабайт XML). Загрузка всего документа в память неэффективна.

**Решение:** Использование `lxml.etree.iterparse` — потоковый парсер, обрабатывающий XML по элементам без загрузки всего документа.

```python
# Алгоритм потокового парсинга YML
def fetch_yml_stream(url: str) -> None:
    response = requests.get(url, stream=True)  # 1. Потоковое скачивание
    response.raw.decode_content = True
    
    context = etree.iterparse(              # 2. Инкрементальный парсинг
        response.raw,
        events=("end",),                    # 3. Событие "конец элемента"
        tag="offer",                        # 4. Фильтр по тегу <offer>
        recover=True,                       # 5. Устойчивость к ошибкам XML
        huge_tree=True                      # 6. Поддержка больших документов
    )
    
    for _, offer_elem in context:
        process_offer(offer_elem)           # 7. Обработка товара
        offer_elem.clear()                  # 8. Очистка памяти
        while offer_elem.getprevious() is not None:
            del offer_elem.getparent()[0]   # 9. Удаление обработанных узлов
```

**Преимущества:**
- Константное потребление памяти независимо от размера файла
- Возможность прерывания обработки (лимит товаров)
- Устойчивость к невалидному XML (`recover=True`)

#### Upsert-стратегия (ON CONFLICT DO UPDATE)

**Проблема:** Повторный запуск сборщика не должен создавать дубликаты.

**Решение:** PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`:

```python
stmt = insert(Product).values(
    external_id=external_id,
    name=name,
    price_in_rub=price,
    # ...
).on_conflict_do_update(
    index_elements=["external_id"],  # Уникальный ключ
    set_={
        "name": name,
        "price_in_rub": price,
        "updated_at": datetime.utcnow(),
    }
)
```

#### Нормализация для сравнения (name_norm)

**Проблема:** Товары в разных каталогах имеют разные названия:
- TDM: `Переходник E27-E40, белый, TDM`
- EKF: `pere odnik e27 e40 bel ekf proxima`

**Решение:** Нормализация названий (транслитерация, удаление спецсимволов):

```python
def _normalize_name(text: str) -> str:
    cleaned = text.lower().replace("ё", "е")
    # Удаление спецсимволов: / , . ( ) [ ] { } : ; | + — – - " '
    cleaned = re.sub(r"[/\\,.()\[\]{}:;|+—–\-\"']", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:600]
```

### 3.2. Разработка программного приложения

#### Структура проекта

```
project/
├── app/
│   ├── __init__.py          # Инициализация пакета
│   ├── database.py          # ORM-модели (Product, ExchangeRate)
│   ├── collector.py         # ETL-процесс сбора данных
│   └── bot.py               # Telegram-бот
├── docker-compose.yml       # Оркестрация контейнеров
├── Dockerfile.app           # Образ Python-приложения
├── requirements.txt         # Зависимости Python
└── .env                     # Переменные окружения
```

#### Описание модулей

| Модуль | Ответственность |
|--------|-----------------|
| `database.py` | ORM-модели, подключение к PostgreSQL, миграции |
| `collector.py` | Сбор курсов валют и товаров, ETL-цикл |
| `bot.py` | Обработка команд Telegram, поиск, сравнение |

#### Ключевые классы

| Класс | Тип | Назначение |
|-------|-----|------------|
| `Product` | ORM Entity | Товар с ценой, источником, метаданными |
| `ExchangeRate` | ORM Entity | Курс валюты к рублю |
| `Router` | Controller | Маршрутизация команд Telegram |
| `Session` | Service | Управление транзакциями БД |

### 3.3. Описание контрольного примера

#### Сценарий 1: Поиск товаров

**Команда:** `/find ekf e27 e40`

**Результат:**
```
🔍 Найдено товаров: 2
Магазин: EKF
Запрос: «e27 e40»

1. pere odnik e27 e40 bel ekf proxima
   💰 191.00 ₽
   🛒 EKF

2. pere odnik e40 e27 bel ekf proxima
   💰 95.68 ₽
   🛒 EKF

💡 Хотите сравнить? /compare ekf tdm e27 e40
```

#### Сценарий 2: Сравнение цен между магазинами

**Команда:** `/compare ekf tdm e27 e40`

**Результат:**
```
⚖️ Сравнение: EKF ↔ TDM Electric
Запрос: «e27 e40»

📦 EKF (2 товара):
1. 95.68 ₽ — pere odnik e40 e27 bel ekf proxima
2. 191.00 ₽ — pere odnik e27 e40 bel ekf proxima

📦 TDM Electric (2 товара):
1. 80.48 ₽ — Переходник E40-E27, белый, TDM
2. 114.95 ₽ — Переходник E27-E40, белый, TDM

🔗 Автосопоставление (по названию):
1) Переходник E40-E27 (TDM) ↔ pere odnik e40 e27 (EKF)
   TDM: 80.48 ₽ | EKF: 95.68 ₽ | Δ: -15.20 ₽ (TDM дешевле)
```

#### Сценарий 3: Статистика системы

**Команда:** `/stats`

**Результат:**
```
📊 Статистика системы

📦 Всего товаров: 59 030
  • EKF: 20 000
  • TDM Electric: 19 025
  • GalaCentre: 14 193
  • TBM Market: 5 792
  • FakeStore: 20

💵 Курс USD: 103.4207 RUB
🕐 Обновлен: 14.12.2024 01:00:00 UTC
```

---

## 4. ДИАГРАММЫ

### 4.1. ER-диаграмма (Entity-Relationship)

Логическая модель данных, описывающая сущности и связи.

```mermaid
erDiagram
    PRODUCTS {
        int id PK "Первичный ключ"
        varchar(255) external_id UK "Уникальный внешний ID"
        varchar(500) name "Название товара"
        varchar(600) name_norm "Нормализованное название"
        float price_original "Оригинальная цена"
        varchar(3) currency "Код валюты (RUB, USD)"
        float price_in_rub "Цена в рублях"
        varchar(100) source_shop "Источник (EKF, TDM...)"
        varchar(1000) url "URL товара"
        varchar(128) barcode "Штрихкод (EAN-13)"
        varchar(128) vendor_code "Артикул поставщика"
        varchar(64) category_id "ID категории"
        datetime updated_at "Время обновления"
    }

    EXCHANGE_RATES {
        int id PK "Первичный ключ"
        varchar(3) currency_code UK "Код валюты"
        float rate "Курс к рублю"
        datetime updated_at "Время обновления"
    }

    PRODUCTS }o--|| EXCHANGE_RATES : "конвертируется по"
```

### 4.2. Диаграмма классов (UML Class Diagram)

Структура классов системы с атрибутами и методами.

```mermaid
classDiagram
    direction TB
    
    class Base {
        <<abstract>>
        +metadata: MetaData
    }
    
    class Product {
        +id: int
        +external_id: str
        +name: str
        +name_norm: str
        +price_original: float
        +currency: str
        +price_in_rub: float
        +source_shop: str
        +url: str
        +barcode: str
        +vendor_code: str
        +category_id: str
        +updated_at: datetime
        +__repr__(): str
    }
    
    class ExchangeRate {
        +id: int
        +currency_code: str
        +rate: float
        +updated_at: datetime
        +__repr__(): str
    }
    
    class Collector {
        -logger: Logger
        -session: Session
        +fetch_exchange_rates(): void
        +fetch_fakestore_products(): void
        +fetch_tbm_products(): void
        +fetch_galacentre_products(): void
        +fetch_tdm_products(): void
        +fetch_ekf_products(): void
        +run_collection_cycle(): void
        -_fetch_yml_stream(url): Response
        -_normalize_name(text): str
        -_parse_price_ru(text): float
    }
    
    class Bot {
        -router: Router
        -bot: Bot
        -dispatcher: Dispatcher
        +cmd_start(message): void
        +cmd_stats(message): void
        +cmd_find(message): void
        +cmd_shops(message): void
        +cmd_compare(message): void
        +handle_callback(callback): void
        -_name_only_score(a, b): float
        -_resolve_shop(alias): str
    }
    
    class DatabaseManager {
        +get_engine(): Engine
        +init_db(engine): void
        +get_session(engine): Session
    }
    
    Base <|-- Product
    Base <|-- ExchangeRate
    
    Collector --> DatabaseManager : uses
    Collector --> Product : creates/updates
    Collector --> ExchangeRate : creates/updates
    
    Bot --> DatabaseManager : uses
    Bot --> Product : queries
    Bot --> ExchangeRate : queries
```

### 4.3. DFD — диаграмма потоков данных

Диаграмма в нотации Gane-Sarson, показывающая потоки данных.

```mermaid
flowchart TB
    subgraph External["Внешние источники"]
        CBR[("ЦБ РФ\n(XML API)")]
        FAKE[("FakeStore\n(JSON API)")]
        TBM[("TBM Market\n(YML)")]
        GALA[("GalaCentre\n(YML)")]
        TDM[("TDM Electric\n(XLS)")]
        EKF[("EKF\n(YML)")]
    end
    
    subgraph Process1["1.0 Сбор курсов валют"]
        P1[[Collector:\nfetch_exchange_rates]]
    end
    
    subgraph Process2["2.0 Сбор товаров"]
        P2[[Collector:\nfetch_*_products]]
    end
    
    subgraph Process3["3.0 Нормализация"]
        P3[[Collector:\n_normalize_name\n_parse_price_ru]]
    end
    
    subgraph Process4["4.0 Сохранение"]
        P4[[Collector:\nupsert to DB]]
    end
    
    subgraph DataStore["Хранилище данных"]
        DB[(PostgreSQL\nproducts\nexchange_rates)]
    end
    
    subgraph Process5["5.0 Поиск и анализ"]
        P5[[Bot:\ncmd_find\ncmd_compare]]
    end
    
    subgraph User["Пользователь"]
        TG[/"Telegram\nклиент"/]
    end
    
    CBR -->|"XML с курсами"| P1
    FAKE -->|"JSON товаров"| P2
    TBM -->|"YML поток"| P2
    GALA -->|"YML поток"| P2
    TDM -->|"XLS файл"| P2
    EKF -->|"YML поток"| P2
    
    P1 -->|"Курсы валют"| P4
    P2 -->|"Сырые данные"| P3
    P3 -->|"Нормализованные\nтовары"| P4
    P4 -->|"INSERT/UPDATE"| DB
    
    TG -->|"Команды\n(/find, /compare)"| P5
    P5 -->|"SELECT запросы"| DB
    DB -->|"Результаты"| P5
    P5 -->|"Ответы"| TG
```

### 4.4. Диаграмма деятельности (Activity Diagram)

Алгоритм работы ETL-процесса сборщика данных.

```mermaid
flowchart TD
    Start((Старт))
    
    Start --> Init["Инициализация:\nподключение к БД"]
    Init --> FetchRates["Получить курсы валют\nот ЦБ РФ"]
    
    FetchRates --> Decision1{Успешно?}
    Decision1 -->|Да| SaveRates["Сохранить курсы в БД"]
    Decision1 -->|Нет| LogError1["Логировать ошибку"]
    
    SaveRates --> FetchProducts
    LogError1 --> FetchProducts
    
    subgraph FetchProducts["Сбор товаров (параллельно)"]
        direction TB
        F1["FakeStore API"]
        F2["TBM Market YML"]
        F3["GalaCentre YML"]
        F4["TDM Electric XLS"]
        F5["EKF YML"]
    end
    
    FetchProducts --> ForEach{{"Для каждого\nисточника"}}
    
    ForEach --> Stream["Потоковое чтение\n(iterparse)"]
    Stream --> Parse["Парсинг элемента\n<offer>"]
    Parse --> Normalize["Нормализация:\n- Транслитерация\n- Очистка символов"]
    Normalize --> Convert["Конвертация валюты\n(если не RUB)"]
    Convert --> Upsert["Upsert в БД\n(ON CONFLICT UPDATE)"]
    Upsert --> HasMore{Ещё товары?}
    HasMore -->|Да| Parse
    HasMore -->|Нет| NextSource{Ещё источники?}
    NextSource -->|Да| ForEach
    NextSource -->|Нет| Commit
    
    Commit["Commit транзакции"]
    Commit --> Sleep["Ожидание\n(1 час)"]
    Sleep --> FetchRates
    
    style Start fill:#90EE90
    style Commit fill:#87CEEB
```

### 4.5. Диаграмма развертывания (Deployment Diagram)

Физическое размещение компонентов системы.

```mermaid
flowchart TB
    subgraph DockerHost["Docker Host (Ubuntu/Windows)"]
        subgraph Network["Docker Network: prices_network"]
            direction TB
            
            subgraph ContainerDB["Container: prices_db"]
                PostgreSQL[(PostgreSQL 15)]
                Vol[(Volume:\npostgres_data)]
            end
            
            subgraph ContainerCollector["Container: prices_collector"]
                Collector[Python 3.11\ncollector.py]
            end
            
            subgraph ContainerBot["Container: prices_bot"]
                Bot[Python 3.11\nbot.py]
            end
            
            subgraph ContainerAdminer["Container: prices_adminer"]
                Adminer[Adminer\nWeb UI]
            end
        end
    end
    
    subgraph External["Внешние сервисы"]
        TelegramAPI[("Telegram\nBot API")]
        DataSources[("Источники данных:\nЦБ РФ, YML-фиды")]
    end
    
    subgraph Client["Клиенты"]
        TelegramClient[/"Telegram\nмессенджер"/]
        Browser[/"Web-браузер\n(Adminer)"/]
    end
    
    Collector <-->|"TCP:5432"| PostgreSQL
    Bot <-->|"TCP:5432"| PostgreSQL
    Adminer <-->|"TCP:5432"| PostgreSQL
    
    Collector <-->|"HTTPS"| DataSources
    Bot <-->|"HTTPS\nLong Polling"| TelegramAPI
    TelegramClient <-->|"HTTPS"| TelegramAPI
    Browser <-->|"HTTP:8080"| Adminer
    
    PostgreSQL --- Vol
    
    style PostgreSQL fill:#336791,color:#fff
    style Collector fill:#3776AB,color:#fff
    style Bot fill:#3776AB,color:#fff
    style TelegramAPI fill:#0088cc,color:#fff
```

---

## 5. ЗАКЛЮЧЕНИЕ

В ходе выполнения курсового проекта была разработана распределенная система сбора и анализа данных о ценах товаров, включающая:

### Достигнутые результаты

1. **Архитектура:** Спроектирована микросервисная архитектура с тремя независимыми компонентами (Collector, Bot, Database), объединенными через Docker Compose.

2. **ETL-процесс:** Реализован эффективный механизм сбора данных:
   - Потоковый парсинг YML (lxml.iterparse) с константным потреблением памяти
   - Поддержка 6 источников данных (API, YML, XLS)
   - Автоматическая конвертация валют по курсу ЦБ РФ
   - Upsert-стратегия для идемпотентных обновлений

3. **Telegram-бот:** Создан пользовательский интерфейс с функциями:
   - Поиск товаров с фильтрацией по магазину
   - Сравнение цен между EKF и TDM Electric
   - Inline-кнопки для быстрого доступа к командам
   - Статистика по загруженным данным

4. **База данных:** Спроектирована схема PostgreSQL с индексами для быстрого поиска по названию, штрихкоду и артикулу.

### Применение распределенных технологий

| Технология | Применение |
|------------|------------|
| Docker Compose | Оркестрация контейнеров, сетевая изоляция |
| PostgreSQL | Централизованное хранилище данных |
| REST/XML API | Интеграция с внешними сервисами |
| Telegram Bot API | Асинхронное взаимодействие с пользователями |
| Long Polling | Получение обновлений от Telegram |

### Перспективы развития

1. Добавление новых источников данных (Wildberries, Ozon)
2. Реализация уведомлений об изменении цен
3. Построение аналитических отчетов (графики, тренды)
4. Миграция на Kubernetes для горизонтального масштабирования

---

## 6. СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ

1. Таненбаум Э., ван Стеен М. Распределенные системы. Принципы и парадигмы. — СПб.: Питер, 2021. — 960 с.

2. Мартин Р. Чистая архитектура. Искусство разработки программного обеспечения. — СПб.: Питер, 2020. — 352 с.

3. Ньюмен С. Создание микросервисов. — СПб.: Питер, 2022. — 624 с.

4. Документация Python 3.11. — URL: https://docs.python.org/3.11/ (дата обращения: 14.12.2024)

5. Документация SQLAlchemy 2.0. — URL: https://docs.sqlalchemy.org/en/20/ (дата обращения: 14.12.2024)

6. Документация aiogram 3.x. — URL: https://docs.aiogram.dev/en/latest/ (дата обращения: 14.12.2024)

7. Документация PostgreSQL 15. — URL: https://www.postgresql.org/docs/15/ (дата обращения: 14.12.2024)

8. Документация Docker. — URL: https://docs.docker.com/ (дата обращения: 14.12.2024)

9. Yandex Market Language (YML). Спецификация формата. — URL: https://yandex.ru/support/market/yml.html (дата обращения: 14.12.2024)

10. API Центрального банка РФ. — URL: https://www.cbr.ru/development/sxml/ (дата обращения: 14.12.2024)

---

## ПРИЛОЖЕНИЕ А. Mermaid-код диаграмм

Для просмотра диаграмм откройте файл `diagrams_viewer.html` в браузере или используйте расширение Mermaid для VS Code / GitHub.

### Примечание по генерации диаграмм

Все диаграммы в этом документе написаны на языке Mermaid и могут быть отрендерены:
- В GitHub/GitLab Markdown
- В VS Code с расширением "Markdown Preview Mermaid Support"
- В онлайн-редакторе https://mermaid.live/
- Через HTML-файл `diagrams_viewer.html` (включен в проект)
