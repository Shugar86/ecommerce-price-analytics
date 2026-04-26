# Прототип FSM-бота для другого проекта (не входит в состав ВКР).
"""
Telegram-бот для клиники beautymedics (Assistant to Dr. Irina).
Исправленная версия с улучшенным UX, форматированием и логикой подбора процедур.
"""

import asyncio
import logging
import os
from enum import Enum, auto
from typing import List, Dict, Any

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIG & DATA ---

class ProcedureType(Enum):
    INJECTION = "Инъекционные методики"
    HARDWARE = "Аппаратные методики"
    CARE = "Уходовые процедуры"
    BODY = "Процедуры для тела"

# База знаний процедур (расширяемая)
PROCEDURES_DB = [
    {
        "name": "Ботулинотерапия (Botox/Disport)",
        "type": ProcedureType.INJECTION,
        "zones": ["лицо", "шея"],
        "goals": ["убрать морщины", "лифтинг"],
        "description": "Коррекция мимических морщин. Расслабляет мышцы, разглаживая кожу.",
        "price": "от 350 руб./ед."
    },
    {
        "name": "Биоревитализация",
        "type": ProcedureType.INJECTION,
        "zones": ["лицо", "шея", "декольте", "руки"],
        "goals": ["увлажнить", "омоложение", "сияние"],
        "description": "Глубокое увлажнение гиалуроновой кислотой. Возвращает коже тонус и сияние.",
        "price": "от 8 000 руб."
    },
    {
        "name": "Контурная пластика (Филлеры)",
        "type": ProcedureType.INJECTION,
        "zones": ["лицо", "губы"],
        "goals": ["убрать морщины", "объем", "асимметрия"],
        "description": "Восполнение объемов, коррекция губ и скул.",
        "price": "от 12 000 руб."
    },
    {
        "name": "Чистка лица (Combi)",
        "type": ProcedureType.CARE,
        "zones": ["лицо", "спина"],
        "goals": ["очистить кожу", "акне"],
        "description": "Комплексное очищение пор + уход. Кожа начинает дышать.",
        "price": "3 500 руб."
    },
    {
        "name": "Пилинг PRX-T33",
        "type": ProcedureType.CARE,
        "zones": ["лицо"],
        "goals": ["омоложение", "акне", "постакне", "сияние"],
        "description": "Всесезонный пилинг без реабилитации. Эффект 'фотошопа'.",
        "price": "5 000 руб."
    },
    {
        "name": "RF-лифтинг",
        "type": ProcedureType.HARDWARE,
        "zones": ["лицо", "тело"],
        "goals": ["лифтинг", "убрать морщины", "тонус"],
        "description": "Безоперационная подтяжка кожи за счет радиочастотного воздействия.",
        "price": "от 4 000 руб."
    },
    {
        "name": "LPG-массаж",
        "type": ProcedureType.BODY,
        "zones": ["тело"],
        "goals": ["похудение", "целлюлит", "дренаж"],
        "description": "Вакуумно-роликовый массаж для коррекции фигуры.",
        "price": "1 500 руб."
    },
]

# --- FSM STATES ---

class ConsultationState(StatesGroup):
    choosing_zone = State()
    choosing_goal = State()

# --- KEYBOARDS ---

def get_zone_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="Лицо"), KeyboardButton(text="Шея")],
        [KeyboardButton(text="Тело"), KeyboardButton(text="Декольте")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_goal_kb(zone: str) -> ReplyKeyboardMarkup:
    # Динамическая клавиатура в зависимости от зоны
    if zone.lower() == "тело":
        buttons = [
            [KeyboardButton(text="Похудение/Целлюлит")],
            [KeyboardButton(text="Увлажнение/Тонус"), KeyboardButton(text="Расслабление")],
        ]
    else:
        buttons = [
            [KeyboardButton(text="Убрать морщины"), KeyboardButton(text="Очистить кожу")],
            [KeyboardButton(text="Увлажнить/Сияние"), KeyboardButton(text="Лифтинг")],
            [KeyboardButton(text="Лечение акне")],
        ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

# --- LOGIC HANDLERS ---

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Начало диалога. Чисто, без лишней воды."""
    await state.clear()
    
    # Приветствие задает "вайб" (professional & caring)
    await message.answer(
        "Здравствуйте! Я виртуальный ассистент доктора Ирины. 👩‍⚕️\n"
        "Помогу подобрать процедуру, которая идеально подойдет именно вам.\n\n"
        "С какой зоной будем работать сегодня?",
        reply_markup=get_zone_kb()
    )
    await state.set_state(ConsultationState.choosing_zone)


@router.message(ConsultationState.choosing_zone)
async def process_zone(message: Message, state: FSMContext) -> None:
    zone = message.text.strip()
    
    # Простая валидация (можно расширить)
    valid_zones = ["лицо", "шея", "тело", "декольте", "руки"]
    if zone.lower() not in valid_zones:
        await message.answer(
            "Пожалуйста, выберите зону из списка ниже или напишите одну из: " + ", ".join(valid_zones),
            reply_markup=get_zone_kb()
        )
        return

    await state.update_data(zone=zone)
    
    # Переход к цели
    await message.answer(
        f"Отлично, работаем с зоной: <b>{zone}</b>. ✨\n"
        "Какого результата вы хотите достичь?",
        parse_mode="HTML",
        reply_markup=get_goal_kb(zone)
    )
    await state.set_state(ConsultationState.choosing_goal)


@router.message(ConsultationState.choosing_goal)
async def process_goal(message: Message, state: FSMContext) -> None:
    goal_raw = message.text.lower()
    data = await state.get_data()
    zone_raw = data.get("zone", "").lower()
    
    await state.clear()  # Сбрасываем состояние, чтобы не "лупить"
    
    # Поиск процедур
    recommendations = []
    
    # Нормализация для поиска (простая эвристика)
    search_tags = []
    if "морщин" in goal_raw: search_tags.append("морщины")
    if "увлажн" in goal_raw: search_tags.append("увлажнить")
    if "очист" in goal_raw or "чист" in goal_raw: search_tags.append("очистить")
    if "акне" in goal_raw: search_tags.append("акне")
    if "лифтинг" in goal_raw: search_tags.append("лифтинг")
    if "похудение" in goal_raw or "целлюлит" in goal_raw: search_tags.append("похудение")
    if "целлюлит" in search_tags: search_tags.append("целлюлит")

    # Если не нашли тегов, ищем просто по вхождению слов
    if not search_tags:
        search_tags = goal_raw.split()

    for proc in PROCEDURES_DB:
        # Проверка зоны
        if not any(z in proc["zones"] for z in [zone_raw]):
            continue
            
        # Проверка цели (хотя бы одно совпадение)
        matches_goal = False
        for tag in search_tags:
            for proc_goal in proc["goals"]:
                if tag in proc_goal or proc_goal in tag:
                    matches_goal = True
                    break
        
        if matches_goal:
            recommendations.append(proc)

    if not recommendations:
        await message.answer(
            "🤔 К сожалению, я не нашла точного совпадения в базе автоматического подбора.\n"
            "Но доктор Ирина точно знает, что делать! Оставьте ваш телефон, и мы свяжемся с вами для консультации.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Формирование красивого ответа
    # Группируем по типу: Инъекции отдельно, Уход отдельно
    grouped = {}
    for r in recommendations:
        t = r["type"].value
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(r)

    response_lines = [f"Для зоны <b>{zone_raw}</b> (цель: {goal_raw}) я рекомендую:\n"]

    for group_name, procs in grouped.items():
        response_lines.append(f"🔹 <b>{group_name}</b>")
        for p in procs:
            response_lines.append(f"• <b>{p['name']}</b>")
            response_lines.append(f"  <i>{p['description']}</i>")
            response_lines.append(f"  💰 {p['price']}")
        response_lines.append("") # Пустая строка между группами

    response_lines.append("✨ <i>Записаться на процедуру или задать вопрос можно кнопкой ниже.</i>")

    # Инлайн клавиатура для действия
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", url="https://t.me/doctor_irina_contact")],
        [InlineKeyboardButton(text="💬 Задать вопрос", url="https://t.me/doctor_irina_contact")]
    ])

    await message.answer("\n".join(response_lines), parse_mode="HTML", reply_markup=kb)


@router.message()
async def handle_unknown(message: Message):
    """
    Обработчик свободного текста.
    Срабатывает, если пользователь пишет что-то вне сценария кнопок.
    """
    # Эвристика: если спрашивают про "цену", "где", "адрес" - отвечаем по существу
    text = message.text.lower()
    
    if "цен" in text or "прайс" in text:
        await message.answer("Полный прайс-лист доступен по ссылке: [ссылка на прайс]")
        return
        
    if "адрес" in text or "где" in text:
        await message.answer("Мы находимся по адресу: ул. Красоты, д. 1. 🏥")
        return

    # Fallback (только если совсем непонятно)
    await message.answer(
        "Доктор Ирина сейчас занята с пациентом, но я передам ей ваш вопрос! 👩‍⚕️\n"
        "Либо попробуйте начать подбор процедуры заново: /start"
    )

# --- MAIN ENTRY POINT ---

async def main() -> None:
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        # Для локального теста можно хардкод, но лучше env
        logger.warning("BOT_TOKEN не найден! Бот не запустится.")
        return

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    logger.info("🌸 BeautyBot запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")

