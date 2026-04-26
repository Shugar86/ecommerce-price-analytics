#!/usr/bin/env python3
"""
Скрипт для проверки работы системы сбора и анализа цен.

Использование:
    python check_system.py
"""

import os
import sys
from datetime import datetime

try:
    from dotenv import load_dotenv
    from sqlalchemy import select, func
    from app.database import get_engine, get_session, ExchangeRate, Product
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Установите зависимости: pip install -r requirements.txt")
    sys.exit(1)


def check_env_variables() -> bool:
    """Проверка наличия необходимых переменных окружения."""
    print("🔍 Проверка переменных окружения...")
    
    load_dotenv()
    
    required_vars = [
        'POSTGRES_USER',
        'POSTGRES_PASSWORD',
        'POSTGRES_DB',
        'POSTGRES_HOST',
        'BOT_TOKEN'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value == 'your_token_here_from_botfather':
            missing_vars.append(var)
        else:
            print(f"  ✅ {var}: {'*' * 8}")
    
    if missing_vars:
        print(f"\n❌ Отсутствуют или не настроены переменные: {', '.join(missing_vars)}")
        print("📝 См. инструкцию в ENV_SETUP.md")
        return False
    
    print("✅ Все переменные окружения настроены\n")
    return True


def check_database_connection() -> bool:
    """Проверка подключения к базе данных."""
    print("🔍 Проверка подключения к БД...")
    
    try:
        engine = get_engine()
        session = get_session(engine)
        
        # Простой запрос для проверки соединения
        session.execute(select(1))
        session.close()
        
        print("✅ Подключение к БД успешно\n")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        print("💡 Убедитесь, что Docker-контейнер с БД запущен: docker-compose up -d db")
        return False


def check_data_collection() -> dict:
    """Проверка наличия собранных данных."""
    print("🔍 Проверка собранных данных...")
    
    try:
        engine = get_engine()
        session = get_session(engine)
        
        # Проверка курсов валют
        usd_rate = session.execute(
            select(ExchangeRate).where(ExchangeRate.currency_code == 'USD')
        ).scalar_one_or_none()
        
        if usd_rate:
            print(f"  ✅ Курс USD: {usd_rate.rate:.4f} RUB")
            print(f"     Обновлен: {usd_rate.updated_at.strftime('%d.%m.%Y %H:%M:%S')} UTC")
        else:
            print("  ⚠️  Курс USD не загружен")
        
        # Подсчет товаров по источникам
        fakestore_count = session.execute(
            select(func.count(Product.id)).where(Product.source_shop == 'FakeStore')
        ).scalar() or 0
        
        tbm_count = session.execute(
            select(func.count(Product.id)).where(Product.source_shop == 'TBM Market')
        ).scalar() or 0
        
        print(f"  📦 Товаров от FakeStore: {fakestore_count}")
        print(f"  📦 Товаров от TBM Market: {tbm_count}")
        print(f"  📦 Всего товаров: {fakestore_count + tbm_count}")
        
        # Время последнего обновления
        last_update = session.execute(
            select(func.max(Product.updated_at))
        ).scalar()
        
        if last_update:
            print(f"  🕐 Последнее обновление: {last_update.strftime('%d.%m.%Y %H:%M:%S')} UTC")
        
        session.close()
        
        print("✅ Данные проверены\n")
        
        return {
            'usd_rate': usd_rate.rate if usd_rate else None,
            'fakestore_count': fakestore_count,
            'tbm_count': tbm_count,
            'total_count': fakestore_count + tbm_count,
            'last_update': last_update
        }
        
    except Exception as e:
        print(f"❌ Ошибка при проверке данных: {e}\n")
        return {}


def main():
    """Главная функция проверки системы."""
    print("=" * 60)
    print("🚀 ПРОВЕРКА СИСТЕМЫ СБОРА И АНАЛИЗА ЦЕН")
    print("=" * 60)
    print()
    
    # Шаг 1: Переменные окружения
    if not check_env_variables():
        print("\n❌ Проверка не пройдена: настройте переменные окружения")
        sys.exit(1)
    
    # Шаг 2: Подключение к БД
    if not check_database_connection():
        print("\n❌ Проверка не пройдена: БД недоступна")
        sys.exit(1)
    
    # Шаг 3: Проверка данных
    data_stats = check_data_collection()
    
    print("=" * 60)
    
    if data_stats.get('total_count', 0) == 0:
        print("⚠️  ПРЕДУПРЕЖДЕНИЕ: Данные еще не собраны")
        print("💡 Подождите 1-2 минуты после запуска docker-compose up")
        print("💡 Проверьте логи: docker-compose logs -f collector")
    else:
        print("✅ СИСТЕМА РАБОТАЕТ КОРРЕКТНО")
        print("\n📋 Следующие шаги:")
        print("   1. Найдите вашего бота в Telegram")
        print("   2. Отправьте команду /start")
        print("   3. Используйте /stats для просмотра статистики")
        print("   4. Используйте /find <запрос> для поиска товаров")
    
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Проверка прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n💀 Критическая ошибка: {e}")
        sys.exit(1)

