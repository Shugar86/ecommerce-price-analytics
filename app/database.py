"""
Модели базы данных для системы сбора и анализа цен.

Описывает структуру таблиц для хранения курсов валют и информации о товарах.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import (
    String,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    create_engine,
    Engine,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger(__name__)

_engine_lock = threading.Lock()
_engine_singleton: Optional[Engine] = None


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


class ExchangeRate(Base):
    """
    Модель для хранения курсов валют.
    
    Attributes:
        id: Уникальный идентификатор записи.
        currency_code: Код валюты (например, 'USD', 'EUR').
        rate: Курс валюты к рублю.
        updated_at: Время последнего обновления курса.
    """
    __tablename__ = 'exchange_rates'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    currency_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<ExchangeRate(currency={self.currency_code}, rate={self.rate})>"


class Product(Base):
    """
    Модель для хранения информации о товарах.
    
    Attributes:
        id: Уникальный идентификатор товара.
        external_id: Внешний идентификатор из источника (уникальный).
        name: Название товара.
        price_original: Оригинальная цена в исходной валюте.
        currency: Код валюты оригинальной цены.
        price_in_rub: Цена в рублях (конвертированная).
        source_shop: Источник данных (например ``'FakeStore'``, ``'TBM Market'``,
            ``'GalaCentre'``, ``'EKF'``, ``'TDM Electric'``).
        url: URL товара (опционально).
        barcode: Штрихкод товара (опционально).
        vendor_code: Артикул/код товара у поставщика (опционально).
        category_id: ID категории из YML (опционально).
        updated_at: Время последнего обновления информации.
    """
    __tablename__ = 'products'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_norm: Mapped[Optional[str]] = mapped_column(String(600), nullable=True)
    price_original: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_in_rub: Mapped[float] = mapped_column(Float, nullable=False)
    source_shop: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vendor_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    category_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Product(name={self.name}, price={self.price_in_rub} RUB, source={self.source_shop})>"

    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="product", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    """
    История изменения цены товара (для графиков, аномалий и прогноза).

    Attributes:
        id: Первичный ключ.
        product_id: Ссылка на товар.
        price_in_rub: Цена в рублях на момент наблюдения.
        source_shop: Источник данных.
        external_id: Внешний идентификатор (дублирует products для удобства отчётов).
        collected_at: Время фиксации точки.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_in_rub: Mapped[float] = mapped_column(Float, nullable=False)
    source_shop: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product", back_populates="price_history")


class PriceAnomaly(Base):
    """
    Результат анализа аномалий цен (ИИ/статистический контур).

    Attributes:
        id: Первичный ключ.
        product_id: Товар.
        detected_at: Время обнаружения.
        anomaly_type: Тип (например spike, fake_discount, zscore).
        severity: Числовая оценка серьёзности (например доля изменения или |z|).
        detail: Текстовое пояснение.
        price_at_detection: Цена на момент анализа.
    """

    __tablename__ = "price_anomalies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    price_at_detection: Mapped[float] = mapped_column(Float, nullable=False)


class ProductMatch(Base):
    """
    Пара сопоставленных товаров из разных источников (NLP / TF-IDF).

    Идентификаторы product_low_id и product_high_id упорядочены (low < high).
    """

    __tablename__ = "product_matches"
    __table_args__ = (
        UniqueConstraint(
            "product_low_id",
            "product_high_id",
            name="uq_product_matches_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_low_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_high_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PriceForecast(Base):
    """
    Прогноз цены по истории (простая регрессия или экстраполяция).
    """

    __tablename__ = "price_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_price_rub: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    forecast_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


def get_database_url() -> str:
    """
    Собирает URL PostgreSQL с экранированием спецсимволов в учётных данных.

    Returns:
        Строка подключения ``postgresql+psycopg2://...``.

    Raises:
        ValueError: Если не заданы обязательные переменные окружения.
    """
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB")

    if not all([user, password, database]):
        raise ValueError(
            "Отсутствуют необходимые переменные окружения: "
            "POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB"
        )

    user_q = quote_plus(user)
    password_q = quote_plus(password)
    database_q = quote_plus(database)
    return f"postgresql+psycopg2://{user_q}:{password_q}@{host}:{port}/{database_q}"


def get_engine() -> Engine:
    """
    Возвращает один экземпляр Engine на процесс (пул соединений переиспользуется).

    Returns:
        Engine: Настроенный движок SQLAlchemy.

    Raises:
        ValueError: Если отсутствуют необходимые переменные окружения.
    """
    global _engine_singleton
    with _engine_lock:
        if _engine_singleton is None:
            _engine_singleton = create_engine(
                get_database_url(),
                echo=False,
                pool_pre_ping=True,
            )
        return _engine_singleton


def dispose_engine() -> None:
    """Закрывает пул соединений (например при остановке веб-приложения)."""
    global _engine_singleton
    with _engine_lock:
        if _engine_singleton is not None:
            _engine_singleton.dispose()
            _engine_singleton = None


def _run_alembic_upgrade() -> None:
    """Применяет миграции Alembic до head (путь относительно корня репозитория)."""
    root = Path(__file__).resolve().parent.parent
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        logger.warning("Файл alembic.ini не найден: %s — пропуск миграций.", ini_path)
        return
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    command.upgrade(cfg, "head")


def init_db(engine: Engine) -> None:
    """
    Инициализирует базу данных, создавая все необходимые таблицы.

    Args:
        engine: Движок SQLAlchemy для подключения к БД.

    Note:
        Безопасна для повторного вызова. После ``create_all`` применяется Alembic ``upgrade head``
        для идемпотентных патчей схемы (индексы, недостающие колонки на старых БД).
    """
    Base.metadata.create_all(engine)
    try:
        _run_alembic_upgrade()
    except SQLAlchemyError as exc:
        logger.warning("Alembic upgrade (SQL): %s", exc)
    except Exception as exc:
        logger.warning("Alembic upgrade: %s", exc)

    logger.info("База данных инициализирована, таблицы и миграции применены.")


def get_session(engine: Engine) -> Session:
    """
    Создает новую сессию для работы с базой данных.
    
    Args:
        engine: Движок SQLAlchemy.
        
    Returns:
        Session: Новая сессия SQLAlchemy.
    """
    return Session(engine, expire_on_commit=False)


if __name__ == "__main__":
    # Тестовый запуск: инициализация БД
    engine = get_engine()
    init_db(engine)

