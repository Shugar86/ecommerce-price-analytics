"""
Telegram-бот для работы с системой сбора и анализа цен.

Предоставляет пользователям доступ к данным о товарах и курсах валют
через удобный интерфейс Telegram.
"""

import asyncio
import html
import logging
import os
from datetime import datetime
import re
from urllib.parse import quote_plus, unquote_plus
from typing import Optional, Iterable

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
from sqlalchemy import select, func

from app.database import get_engine, init_db, get_session, ExchangeRate, Product

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация роутера для обработчиков
router = Router()

def _h(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return html.escape(text, quote=False)

def _ha(text: str) -> str:
    """Escape text for Telegram HTML attributes (e.g. href)."""
    return html.escape(text, quote=True)

_SHOP_ALIASES: dict[str, str] = {
    "ekf": "EKF",
    "tdm": "TDM Electric",
    "tdme": "TDM Electric",
    "tbm": "TBM Market",
    "gala": "GalaCentre",
    "galacentre": "GalaCentre",
    "fakestore": "FakeStore",
}

_LAT_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_MODEL_TOKEN_RE = re.compile(r"(?=.*[a-z])(?=.*\\d)[a-z0-9]{3,32}$", re.IGNORECASE)

_RU_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ы": "y", "э": "e", "ю": "yu", "я": "ya", "ь": "", "ъ": "",
}


def _to_latin(text: str) -> str:
    t = text.lower().replace("ё", "е")
    out: list[str] = []
    for ch in t:
        if "а" <= ch <= "я" or ch in ("ё", "ь", "ъ"):
            out.append(_RU_TO_LAT.get(ch, ""))
        else:
            out.append(ch)
    return "".join(out)


def _normalize_for_match(text: str) -> str:
    """Normalize + transliterate to latin space for cross-shop matching."""
    t = _to_latin(text)
    t = (
        t.replace("×", "x")
        .replace("/", " ")
        .replace("\\\\", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("[", " ")
        .replace("]", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("|", " ")
        .replace("+", " ")
        .replace("—", " ")
        .replace("–", " ")
        .replace("-", " ")
        .replace("\"", " ")
        .replace("'", " ")
    )
    t = re.sub(r"\\s+", " ", t).strip()
    return t


def _tokens_lat(text: str) -> set[str]:
    norm = _normalize_for_match(text)
    toks = {t for t in _LAT_TOKEN_RE.findall(norm) if len(t) >= 3}
    return toks


def _model_tokens(tokens: Iterable[str]) -> set[str]:
    return {t for t in tokens if _MODEL_TOKEN_RE.match(t)}


def _word_tokens(tokens: Iterable[str]) -> set[str]:
    out = set()
    for t in tokens:
        if t.isdigit():
            continue
        if any("a" <= ch <= "z" for ch in t) and len(t) >= 5:
            out.add(t)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _name_only_score(a: str, b: str) -> float:
    """Name-only similarity tuned for dirty RU data + EKF latin slugs."""
    ta = _tokens_lat(a)
    tb = _tokens_lat(b)
    ma, mb = _model_tokens(ta), _model_tokens(tb)
    wa, wb = _word_tokens(ta), _word_tokens(tb)

    # Prefer model tokens if present
    if ma and mb:
        if not (ma & mb):
            return 0.0
        return 0.8 * _jaccard(ma, mb) + 0.2 * _jaccard(wa, wb)

    # Fallback: meaningful words
    if len(wa) >= 2 and len(wb) >= 2 and len(wa & wb) >= 1:
        return _jaccard(wa, wb)
    return 0.0


def _resolve_shop(alias: str) -> Optional[str]:
    a = (alias or "").strip().lower()
    if not a:
        return None
    return _SHOP_ALIASES.get(a)


def _compare_help_block() -> str:
    # Concrete examples that work well for EKF↔TDM (model tokens)
    examples = [
        "e14 gu10",
        "e27 e40",
        "e14 e27",
        "5pin ip68",
        "st64 e27",
    ]
    lines = [
        "⚖️ <b>/compare</b> — сравнение цен между магазинами (по наименованиям)\n",
        "<b>Быстрый старт (рекомендуем EKF ↔ TDM):</b>",
        "• <code>/compare ekf tdm e14 gu10</code>",
        "• <code>/compare ekf tdm e27 e40</code>",
        "• <code>/compare ekf tdm 5pin ip68</code>",
        "",
        "<b>Если лень выбирать магазины:</b>",
        "• <code>/compare e27 e40</code> (по умолчанию сравниваем EKF ↔ TDM)",
        "",
        "<b>Подсказки “что сравнивать”:</b>",
        "Используй модельные токены (буквы+цифры): " + ", ".join(f"<code>{e}</code>" for e in examples),
        "",
        "📌 Команда: <code>/shops</code> — список источников и сколько товаров загружено.",
    ]
    return "\n".join(lines)


def _compare_help_kb() -> InlineKeyboardMarkup:
    def cb(shop_a: str, shop_b: str, query: str) -> str:
        return f"cmp:{shop_a}:{shop_b}:{quote_plus(query)}"

    rows = [
        [
            InlineKeyboardButton(text="EKF ↔ TDM: e14 gu10", callback_data=cb("ekf", "tdm", "e14 gu10")),
            InlineKeyboardButton(text="EKF ↔ TDM: e27 e40", callback_data=cb("ekf", "tdm", "e27 e40")),
        ],
        [
            InlineKeyboardButton(text="EKF ↔ TDM: 5pin ip68", callback_data=cb("ekf", "tdm", "5pin ip68")),
            InlineKeyboardButton(text="EKF ↔ TDM: st64 e27", callback_data=cb("ekf", "tdm", "st64 e27")),
        ],
        [
            InlineKeyboardButton(text="📦 Показать магазины", callback_data="shops"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _shop_emoji(shop: str) -> str:
    if shop in ("EKF", "TDM Electric"):
        return "🏭"
    if shop == "TBM Market":
        return "🏪"
    if shop == "GalaCentre":
        return "🛒"
    if shop == "FakeStore":
        return "🌍"
    return "🏷️"


async def _run_compare(message: Message, *, shop_a: str, shop_b: str, query: str) -> None:
    """Shared compare logic for both /compare and button callbacks."""
    def _fmt_price(v: float) -> str:
        return f"{v:,.2f}".replace(",", " ")

    q_low = query.lower().replace("ё", "е")
    ban_terms: tuple[str, ...] = ()
    if "холодил" in q_low:
        ban_terms = ("магнит", "открываш")

    engine = get_engine()
    session = get_session(engine)
    try:
        limit_per_shop = 40
        q_norm = query.lower().replace("ё", "е")

        a_items = session.execute(
            select(Product)
            .where(Product.source_shop == shop_a, Product.name_norm.ilike(f"%{q_norm}%"))
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()

        b_items = session.execute(
            select(Product)
            .where(Product.source_shop == shop_b, Product.name_norm.ilike(f"%{q_norm}%"))
            .order_by(Product.price_in_rub)
            .limit(limit_per_shop)
        ).scalars().all()

        def _filter(items: list[Product]) -> list[Product]:
            if not ban_terms:
                return items
            out: list[Product] = []
            for it in items:
                n = it.name.lower().replace("ё", "е")
                if any(bt in n for bt in ban_terms):
                    continue
                out.append(it)
            return out

        a_items = _filter(a_items)
        b_items = _filter(b_items)

        if not a_items and not b_items:
            await message.answer(
                f"😞 По запросу <b>«{_h(query)}»</b> ничего не найдено в <b>{_h(shop_a)}</b> и <b>{_h(shop_b)}</b>.\n\n"
                "Попробуйте модельные токены (буквы+цифры), например: <code>e14 gu10</code>, <code>e27 e40</code>, <code>5pin ip68</code>.",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return

        lines: list[str] = [
            f"🔎 <b>Сравнение:</b> «{_h(query)}»",
            f"🧩 <b>Пара магазинов:</b> {_h(shop_a)} ↔ {_h(shop_b)}",
            "",
        ]

        lines.append(f"<b>{_shop_emoji(shop_a)} {_h(shop_a)} (топ по цене):</b>")
        for i, t in enumerate(a_items[:10], start=1):
            lines.append(f"{i}. {_fmt_price(t.price_in_rub)} ₽ — <i>{_h(t.name[:120])}</i>")
        if not a_items:
            lines.append("<i>Нет результатов.</i>")
        lines.append("")

        lines.append(f"<b>{_shop_emoji(shop_b)} {_h(shop_b)} (топ по цене):</b>")
        for i, g in enumerate(b_items[:10], start=1):
            lines.append(f"{i}. {_fmt_price(g.price_in_rub)} ₽ — <i>{_h(g.name[:120])}</i>")
        if not b_items:
            lines.append("<i>Нет результатов.</i>")
        lines.append("")

        if a_items and b_items:
            used_b: set[int] = set()
            pairs: list[tuple[Product, Product, float]] = []

            for a in a_items:
                a_type = _item_type(a.name)
                best_b: Optional[Product] = None
                best_s = 0.0
                for b in b_items:
                    if b.id in used_b:
                        continue
                    if _item_type(b.name) != a_type and a_type in ("fridge", "microwave"):
                        continue
                    s = _name_only_score(a.name, b.name)
                    if s > best_s:
                        best_s = s
                        best_b = b
                if best_b is not None and best_s >= 0.35:
                    used_b.add(best_b.id)
                    pairs.append((a, best_b, best_s))

            pairs.sort(key=lambda x: (-x[2], abs(x[0].price_in_rub - x[1].price_in_rub)))

            if pairs:
                lines.append("<b>Автосопоставление (по наименованиям):</b>")
                lines.append("<i>Лучше всего работают модельные токены (буквы+цифры): E14, GU10, E27, E40, 5PIN, IP68, ST64…</i>")
                lines.append("")
                for i, (a, b, score) in enumerate(pairs[:7], start=1):
                    dt = a.price_in_rub - b.price_in_rub
                    lines.append(f"{i}) <b>match={score:.2f}</b>")
                    lines.append(f"   <b>{_h(shop_a)}</b>: {_fmt_price(a.price_in_rub)} ₽ — <i>{_h(a.name[:120])}</i>")
                    lines.append(f"   <b>{_h(shop_b)}</b>: {_fmt_price(b.price_in_rub)} ₽ — <i>{_h(b.name[:120])}</i>")
                    lines.append(f"   Δ ({_h(shop_a)} - {_h(shop_b)}): <b>{_fmt_price(dt)} ₽</b>")
                    lines.append("")
            else:
                lines.append("⚠️ Автосопоставление не нашло уверенных пар. Уточните запрос (бренд/модель, типа <code>e27 e40</code>).")

        await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

    finally:
        session.close()

def _tokenize_for_match(text: str) -> set[str]:
    """Tokenize product name for rough matching between different shops.

    This is a pragmatic heuristic (no ML): it helps pair similar items (e.g. microwaves/fridges)
    across two RU catalogs even when barcodes do not match.
    """
    cleaned = (
        text.lower()
        .replace("ё", "е")
        .replace("/", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    # Drop very short tokens to reduce noise.
    return {p for p in parts if len(p) >= 3}


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity over tokens."""
    ta = _tokenize_for_match(a)
    tb = _tokenize_for_match(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta.intersection(tb))
    union = len(ta.union(tb))
    return inter / union


def _item_type(name: str) -> str:
    """Rough product type classifier for safer pairing.

    Goal: avoid pairing 'Холодильник' with 'магнит на холодильник' just because of a shared word.
    """
    n = name.lower().replace("ё", "е")
    if "магнит" in n:
        return "magnet"
    if "открываш" in n:
        return "opener"
    if "микроволновка" in n:
        return "microwave"
    if "тарелка" in n and "микроволнов" in n:
        return "microwave_plate"
    if "холодильник" in n or "холодильная камера" in n:
        return "fridge"
    if "контейнер" in n:
        return "container"
    if "поглот" in n or "освеж" in n:
        return "odor"
    return "other"


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """
    Обработчик команды /start.
    
    Отправляет приветственное сообщение с кратким описанием
    возможностей бота и списком доступных команд.
    
    Args:
        message: Входящее сообщение от пользователя.
    """
    welcome_text = (
        "👋 <b>Добро пожаловать в систему сбора и анализа цен!</b>\n\n"
        "Этот бот предоставляет доступ к актуальной информации о товарах "
        "с различных торговых площадок и курсах валют.\n\n"
        "📌 <b>Доступные команды:</b>\n\n"
        "/start - Показать это сообщение\n"
        "/stats - Показать статистику по товарам и курсам валют\n"
        "/shops - Показать какие магазины загружены (и сколько товаров)\n"
        "/find &lt;название&gt; - Найти товары по названию\n\n"
        "/compare - Подсказка, что и как сравнивать\n"
        "/compare &lt;запрос&gt; - Быстро сравнить (по умолчанию EKF ↔ TDM)\n"
        "/compare ekf tdm &lt;запрос&gt; - Явно выбрать пару магазинов\n\n"
        "💡 <b>Пример использования:</b>\n"
        "<code>/find laptop</code> - поиск ноутбуков\n"
        "<code>/find телефон</code> - поиск телефонов\n\n"
        "Данные обновляются автоматически каждый час."
    )
    
    await message.answer(welcome_text, parse_mode="HTML")
    logger.info(f"Пользователь {message.from_user.id} выполнил команду /start")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """
    Обработчик команды /stats.
    
    Показывает статистику:
    - Количество товаров по каждому источнику
    - Текущий курс USD к рублю
    - Время последнего обновления данных
    
    Args:
        message: Входящее сообщение от пользователя.
    """
    try:
        # Получаем движок и сессию БД
        engine = get_engine()
        session = get_session(engine)
        
        try:
            # Подсчет товаров по источникам (динамически, чтобы не забывать новые магазины)
            rows = session.execute(
                select(Product.source_shop, func.count(Product.id))
                .group_by(Product.source_shop)
                .order_by(func.count(Product.id).desc())
            ).all()
            per_shop = [(r[0], int(r[1])) for r in rows if r and r[0]]
            total_count = sum(c for _, c in per_shop)
            
            # Получение текущего курса USD
            stmt_usd = select(ExchangeRate).where(
                ExchangeRate.currency_code == 'USD'
            )
            usd_rate_obj = session.execute(stmt_usd).scalar_one_or_none()
            
            if usd_rate_obj:
                usd_rate = usd_rate_obj.rate
                usd_updated = usd_rate_obj.updated_at.strftime('%d.%m.%Y %H:%M:%S')
                currency_info = (
                    f"💵 <b>Курс USD:</b> {usd_rate:.4f} RUB\n"
                    f"🕐 <b>Обновлен:</b> {usd_updated} UTC"
                )
            else:
                currency_info = "❌ <b>Курс USD:</b> Не загружен"
            
            # Получение времени последнего обновления товаров
            stmt_last_update = select(func.max(Product.updated_at))
            last_update = session.execute(stmt_last_update).scalar()
            
            if last_update:
                last_update_str = last_update.strftime('%d.%m.%Y %H:%M:%S')
                update_info = f"🕐 <b>Последнее обновление товаров:</b> {last_update_str} UTC"
            else:
                update_info = "❌ <b>Товары:</b> Еще не загружены"
            
            # Формирование ответа
            stats_text = (
                "📊 <b>Статистика системы</b>\n\n"
                f"📦 <b>Всего товаров:</b> {total_count}\n"
                + "".join([f"  • {_h(s)}: {c}\n" for s, c in per_shop])
                + "\n"
                f"{currency_info}\n\n"
                f"{update_info}"
            )
            
            await message.answer(stats_text, parse_mode="HTML")
            logger.info(f"Пользователь {message.from_user.id} запросил статистику")
            
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f"Ошибка при обработке /stats: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении статистики. "
            "Попробуйте позже или обратитесь к администратору."
        )


@router.message(Command("shops"))
async def cmd_shops(message: Message) -> None:
    """List loaded shops and item counts. Helps users understand what to compare."""
    try:
        engine = get_engine()
        session = get_session(engine)
        try:
            rows = session.execute(
                select(Product.source_shop, func.count(Product.id))
                .group_by(Product.source_shop)
                .order_by(func.count(Product.id).desc())
            ).all()
            per_shop = [(r[0], int(r[1])) for r in rows if r and r[0]]
            if not per_shop:
                await message.answer("❌ В БД пока нет товаров. Подождите, пока collector загрузит данные.")
                return

            lines = ["🏪 <b>Загруженные магазины:</b>\n"]
            for s, c in per_shop:
                alias = next((k for k, v in _SHOP_ALIASES.items() if v == s), None)
                if alias:
                    lines.append(f"- <b>{_h(s)}</b> (<code>{alias}</code>): {c}")
                else:
                    lines.append(f"- <b>{_h(s)}</b>: {c}")

            lines.append("\n<b>Рекомендуем для сравнения по наименованиям:</b> <code>ekf</code> ↔ <code>tdm</code>")
            lines.append("Подсказка: <code>/compare</code>")

            await message.answer("\n".join(lines), parse_mode="HTML")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Ошибка при обработке /shops: {e}")
        await message.answer("❌ Не удалось получить список магазинов. Попробуйте позже.")


@router.message(Command("find"))
async def cmd_find(message: Message) -> None:
    """
    Обработчик команды /find <запрос>.
    
    Выполняет поиск товаров по названию (регистронезависимый).
    Возвращает до 10 наиболее релевантных результатов.
    
    Args:
        message: Входящее сообщение от пользователя.
    """
    try:
        parts = (message.text or "").split()

        if len(parts) < 2:
            await message.answer(
                "⚠️ <b>Использование:</b> /find &lt;запрос&gt;\n\n"
                "Можно ограничить магазином:\n"
                "<code>/find ekf e27 e40</code>\n"
                "<code>/find tdm e14 gu10</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>/find laptop</code>\n"
                "<code>/find телефон</code>\n"
                "<code>/find e27 e40</code>",
                parse_mode="HTML",
            )
            return

        # /find [shop] query...
        shop_filter: Optional[str] = None
        maybe_shop = _resolve_shop(parts[1])
        if maybe_shop and len(parts) >= 3:
            shop_filter = maybe_shop
            query = " ".join(parts[2:]).strip()
        else:
            query = " ".join(parts[1:]).strip()
        
        if len(query) < 2:
            await message.answer(
                "⚠️ Запрос слишком короткий. Введите минимум 2 символа."
            )
            return
        
        logger.info(f"Пользователь {message.from_user.id} ищет: {query}")
        
        # Получаем движок и сессию БД
        engine = get_engine()
        session = get_session(engine)
        
        try:
            q_norm = query.lower().replace("ё", "е")

            if shop_filter:
                stmt = (
                    select(Product)
                    .where(Product.source_shop == shop_filter, Product.name_norm.ilike(f"%{q_norm}%"))
                    .order_by(Product.price_in_rub)
                    .limit(15)
                )
                results = session.execute(stmt).scalars().all()
            else:
                # Give users a diverse view (few from each shop)
                results: list[Product] = []
                for s in ("EKF", "TDM Electric", "TBM Market", "GalaCentre", "FakeStore"):
                    rows = session.execute(
                        select(Product)
                        .where(Product.source_shop == s, Product.name_norm.ilike(f"%{q_norm}%"))
                        .order_by(Product.price_in_rub)
                        .limit(4)
                    ).scalars().all()
                    results.extend(rows)
            
            if not results:
                await message.answer(
                    f"😞 По запросу <b>«{_h(query)}»</b> ничего не найдено.\n\n"
                    "Попробуйте:\n"
                    "• Изменить запрос\n"
                    "• Использовать более короткие ключевые слова\n"
                    "• Проверить правильность написания\n\n"
                    "💡 Для EKF↔TDM часто лучше использовать модельные токены (буквы+цифры): <code>e27 e40</code>, <code>e14 gu10</code>, <code>5pin ip68</code>.",
                    parse_mode="HTML"
                )
                return
            
            # Формирование ответа с результатами
            response_text = (
                f"🔍 <b>Найдено:</b> {len(results)}\n"
                f"<b>Запрос:</b> «{_h(query)}»\n"
                + (f"<b>Магазин:</b> {_h(shop_filter)}\n" if shop_filter else "")
                + "\n"
            )
            
            for idx, product in enumerate(results, start=1):
                # Форматирование цены
                price_rub_formatted = f"{product.price_in_rub:,.2f}".replace(',', ' ')
                
                # Информация об оригинальной цене
                if product.currency != 'RUB':
                    original_price_formatted = f"{product.price_original:.2f}"
                    price_info = (
                        f"{price_rub_formatted} ₽ "
                        f"({original_price_formatted} {product.currency})"
                    )
                else:
                    price_info = f"{price_rub_formatted} ₽"
                
                # Ограничение длины названия товара
                product_name = product.name[:100] + "..." if len(product.name) > 100 else product.name
                product_name_safe = _h(product_name)
                
                source_emoji = _shop_emoji(product.source_shop)
                
                response_text += (
                    f"{idx}. <b>{product_name_safe}</b>\n"
                    f"   💰 {price_info}\n"
                    f"   {source_emoji} {_h(product.source_shop)}\n"
                )
                
                if product.url:
                    response_text += f"   🔗 <a href='{_ha(product.url)}'>Ссылка</a>\n"
                
                response_text += "\n"
            
            # Telegram ограничивает длину сообщения 4096 символами
            if len(response_text) > 4000:
                response_text = response_text[:3900] + "\n\n...\n\n⚠️ Результаты обрезаны. Уточните запрос."

            response_text += (
                "💡 Хочешь сравнить цены между EKF и TDM по этому запросу?\n"
                f"<code>/compare ekf tdm { _h(query) }</code>\n"
            )

            await message.answer(response_text, parse_mode="HTML", disable_web_page_preview=True)
            logger.info(f"Отправлено {len(results)} результатов пользователю {message.from_user.id}")
            
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f"Ошибка при обработке /find: {e}")
        await message.answer(
            "❌ Произошла ошибка при поиске товаров. "
            "Попробуйте позже или обратитесь к администратору."
        )


@router.message(Command("compare"))
async def cmd_compare(message: Message) -> None:
    """
    User-friendly compare.

    Supported:
    - /compare                      -> help + examples
    - /compare <query>              -> compare EKF ↔ TDM by default
    - /compare <shopA> <shopB> <q>  -> explicit shops (aliases: ekf, tdm, tbm, gala, fakestore)
    """
    def _fmt_price(v: float) -> str:
        return f"{v:,.2f}".replace(",", " ")

    try:
        raw = (message.text or "").strip()
        parts = raw.split()
        if len(parts) == 1:
            await message.answer(
                _compare_help_block(),
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=_compare_help_kb(),
            )
            return

        # Parse: /compare [shopA shopB] query...
        shop_a = "EKF"
        shop_b = "TDM Electric"
        query_parts = parts[1:]

        if len(query_parts) >= 3:
            maybe_a = _resolve_shop(query_parts[0])
            maybe_b = _resolve_shop(query_parts[1])
            if maybe_a and maybe_b:
                shop_a, shop_b = maybe_a, maybe_b
                query_parts = query_parts[2:]

        if not query_parts:
            await message.answer(
                _compare_help_block(),
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=_compare_help_kb(),
            )
            return

        query = " ".join(query_parts).strip()
        if len(query) < 2:
            await message.answer("⚠️ Запрос слишком короткий. Введите минимум 2 символа.")
            return

        await _run_compare(message, shop_a=shop_a, shop_b=shop_b, query=query)

    except Exception as e:
        logger.error(f"Ошибка при обработке /compare: {e}")
        await message.answer("❌ Произошла ошибка при сравнении товаров. Попробуйте позже.")


@router.callback_query(F.data == "shops")
async def cb_shops(call: CallbackQuery) -> None:
    await call.answer()
    try:
        engine = get_engine()
        session = get_session(engine)
        try:
            rows = session.execute(
                select(Product.source_shop, func.count(Product.id))
                .group_by(Product.source_shop)
                .order_by(func.count(Product.id).desc())
            ).all()
            per_shop = [(r[0], int(r[1])) for r in rows if r and r[0]]
            if not per_shop:
                await call.message.answer("❌ В БД пока нет товаров. Подождите, пока collector загрузит данные.")
                return

            lines = ["🏪 <b>Загруженные магазины:</b>\n"]
            for s, c in per_shop:
                alias = next((k for k, v in _SHOP_ALIASES.items() if v == s), None)
                if alias:
                    lines.append(f"- <b>{_h(s)}</b> (<code>{alias}</code>): {c}")
                else:
                    lines.append(f"- <b>{_h(s)}</b>: {c}")
            lines.append("\nПодсказка: <code>/compare</code>")
            await call.message.answer("\n".join(lines), parse_mode="HTML")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Ошибка callback shops: {e}")


@router.callback_query(F.data.startswith("cmp:"))
async def cb_compare(call: CallbackQuery) -> None:
    await call.answer()
    try:
        parts = (call.data or "").split(":", maxsplit=3)
        if len(parts) != 4:
            return
        _, a_alias, b_alias, q_enc = parts
        shop_a = _resolve_shop(a_alias) or "EKF"
        shop_b = _resolve_shop(b_alias) or "TDM Electric"
        query = unquote_plus(q_enc or "").strip()
        if not query:
            return
        await _run_compare(call.message, shop_a=shop_a, shop_b=shop_b, query=query)
    except Exception as e:
        logger.error(f"Ошибка callback compare: {e}")


@router.message()
async def handle_unknown(message: Message) -> None:
    """
    Обработчик неизвестных команд и сообщений.
    
    Информирует пользователя о том, что команда не распознана,
    и напоминает список доступных команд.
    
    Args:
        message: Входящее сообщение от пользователя.
    """
    await message.answer(
        "❓ Команда не распознана.\n\n"
        "Используйте /start для просмотра списка доступных команд."
    )


async def main() -> None:
    """
    Главная асинхронная функция для запуска бота.
    
    Инициализирует бота, регистрирует обработчики и запускает polling.
    """
    # Получение токена бота из переменных окружения
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token or bot_token == 'your_token_here_from_botfather':
        logger.critical("❌ BOT_TOKEN не установлен в переменных окружения!")
        raise ValueError(
            "Необходимо установить BOT_TOKEN в файле .env. "
            "Получите токен у @BotFather в Telegram."
        )
    
    # Инициализация БД (создание таблиц, если их нет)
    try:
        engine = get_engine()
        init_db(engine)
        logger.info("✅ Подключение к БД установлено")
    except Exception as e:
        logger.critical(f"❌ Ошибка подключения к БД: {e}")
        raise
    
    # Создание экземпляров бота и диспетчера
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    
    # Регистрация роутера
    dp.include_router(router)
    
    logger.info("🤖 Telegram-бот запущен и ожидает сообщений...")
    
    try:
        # Запуск polling (бесконечный опрос серверов Telegram)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"💀 Критическая ошибка: {e}")
        raise

