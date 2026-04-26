#!/usr/bin/env python3
"""
Скрипт для проверки структуры проекта.
Выводит дерево файлов с описанием назначения каждого файла.
"""

import os
from pathlib import Path


def print_tree():
    """Выводит структуру проекта с описаниями."""
    
    structure = {
        "app/": {
            "description": "📦 Основной пакет приложения",
            "files": {
                "__init__.py": "Инициализация Python пакета",
                "database.py": "🗄️ Модели SQLAlchemy (ExchangeRate, Product) + init_db()",
                "collector.py": "🔄 ETL-процесс: сбор данных от 3 источников",
                "bot.py": "🤖 Telegram-бот на Aiogram 3.x (команды /start, /stats, /find)"
            }
        },
        "docker-compose.yml": "🐳 Оркестрация 4 контейнеров: db, adminer, collector, bot",
        "Dockerfile.app": "📦 Docker-образ для Python-приложений (collector + bot)",
        "requirements.txt": "📋 Зависимости Python с версиями",
        "env.example": "🔑 Шаблон переменных окружения (токены, пароли)",
        ".env": "🔒 Секретные данные (НЕ в git!)",
        ".gitignore": "🚫 Исключения для git",
        "README.md": "📖 Быстрый старт (5 минут до запуска)",
        "README_REPORT.md": "📝 Полная документация для пояснительной записки (10 разделов + диаграммы)",
        "ENV_SETUP.md": "⚙️ Пошаговая инструкция по созданию .env файла",
        "FAQ.md": "❓ Часто задаваемые вопросы и решения проблем",
        "SUMMARY.md": "📊 Краткое резюме проекта (метрики, чек-листы)",
        "COMMANDS.md": "⌨️ Справочник команд Docker и SQL",
        "check_system.py": "🔍 Скрипт автоматической проверки работы системы",
        "PROJECT_FILES.py": "📁 Этот файл - обзор структуры проекта"
    }
    
    print("=" * 70)
    print("📂 СТРУКТУРА ПРОЕКТА: Распределенная система сбора цен")
    print("=" * 70)
    print()
    
    total_files = 0
    
    for item, details in structure.items():
        if isinstance(details, dict) and "description" in details:
            # Директория
            print(f"📁 {item}")
            print(f"   {details['description']}")
            print()
            
            for filename, desc in details["files"].items():
                status = "✅" if os.path.exists(f"{item}{filename}") else "❌"
                print(f"   {status} {filename}")
                print(f"      → {desc}")
                print()
                total_files += 1
        else:
            # Файл в корне
            status = "✅" if os.path.exists(item) else "❌"
            print(f"{status} {item}")
            print(f"   → {details}")
            print()
            total_files += 1
    
    print("=" * 70)
    print(f"📊 Всего файлов в проекте: {total_files}")
    print("=" * 70)
    print()
    
    # Проверка наличия .env
    if not os.path.exists(".env"):
        print("⚠️  ВНИМАНИЕ: Файл .env не найден!")
        print("   Создайте его по инструкции из ENV_SETUP.md")
        print()
    
    # Проверка Docker
    docker_compose_exists = os.path.exists("docker-compose.yml")
    dockerfile_exists = os.path.exists("Dockerfile.app")
    
    if docker_compose_exists and dockerfile_exists:
        print("✅ Docker-конфигурация найдена")
        print("   Готово к запуску: docker-compose up -d")
    else:
        print("❌ Отсутствуют файлы Docker-конфигурации")
    
    print()


def check_file_sizes():
    """Проверяет размеры ключевых файлов."""
    print("=" * 70)
    print("📏 РАЗМЕРЫ ФАЙЛОВ")
    print("=" * 70)
    print()
    
    key_files = [
        "app/database.py",
        "app/collector.py",
        "app/bot.py",
        "README_REPORT.md",
        "docker-compose.yml"
    ]
    
    for filepath in key_files:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            lines = 0
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = len(f.readlines())
            except:
                pass
            
            print(f"📄 {filepath}")
            print(f"   Размер: {size:,} байт")
            if lines > 0:
                print(f"   Строк: {lines}")
            print()
    
    print()


def main():
    """Главная функция."""
    print()
    print_tree()
    check_file_sizes()
    
    print("=" * 70)
    print("📚 ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ")
    print("=" * 70)
    print()
    print("Для запуска системы:")
    print("  1. Создайте .env файл (см. ENV_SETUP.md)")
    print("  2. Выполните: docker-compose up -d")
    print("  3. Проверьте: python check_system.py")
    print()
    print("Полная документация:")
    print("  • README.md - Быстрый старт")
    print("  • README_REPORT.md - Для пояснительной записки")
    print("  • FAQ.md - Решение проблем")
    print("  • COMMANDS.md - Справочник команд")
    print()
    print("Контакты:")
    print("  При проблемах изучите логи: docker-compose logs")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()

