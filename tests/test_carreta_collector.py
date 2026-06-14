"""Тесты парсера CSV CARRETA."""

from __future__ import annotations

import pytest

from app.collectors.carreta import parse_carreta_csv_text


def test_parse_carreta_valid_row_cp1251_header() -> None:
    """Валидная строка после декодирования даёт оффер с ценой и кодом."""
    text = (
        "Производитель;Код;Наименование;В наличии;Цена;Заказ от;Срок мин;Срок макс\n"
        "ACME;A1;Им тест  номенклатуры;1;125,50;1;0;1\n"
    )
    rows, skipped = parse_carreta_csv_text(text)
    assert skipped == 0
    assert len(rows) == 1
    assert rows[0]["name"].startswith("Им тест")
    assert rows[0]["price_rub"] == pytest.approx(125.50)
    assert rows[0]["vendor_code"] == "A1"
    assert rows[0]["brand"] == "ACME"
    assert rows[0]["availability"] is True


def test_parse_carreta_skips_bad_price_and_empty_name() -> None:
    """Битая цена и пустое имя увеличивают счётчик пропусков."""
    text = (
        "Производитель;Код;Наименование;В наличии;Цена\n"
        ";B1;;;not_a_price\n"
        ";;;1;99\n"
    )
    rows, skipped = parse_carreta_csv_text(text)
    assert rows == []
    assert skipped >= 2


def test_parse_carreta_respects_limit() -> None:
    """Параметр max_rows ограничивает число валидных строк."""
    lines = ["Производитель;Код;Наименование;Цена"]
    for i in range(5):
        lines.append(f"X;C{i};Товар номер {i};{10 + i}.00")
    text = "\n".join(lines)
    rows, _ = parse_carreta_csv_text(text, max_rows=3)
    assert len(rows) == 3


def test_availability_column_is_bool_not_free_text() -> None:
    """«В наличии» → bool; сроки не склеиваются в строку (тип колонки БД — boolean)."""
    text = (
        "Производитель;Код;Наименование;В наличии;Цена;Заказ от;Срок мин;Срок макс\n"
        "X;Z1;Товар;0;10.00;1;0;0\n"
    )
    rows, skipped = parse_carreta_csv_text(text)
    assert skipped == 0
    assert rows[0]["availability"] is False

