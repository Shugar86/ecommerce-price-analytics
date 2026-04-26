"""Тесты логики текстового поиска по товарам (в т.ч. при NULL в name_norm)."""

from __future__ import annotations

from sqlalchemy import select

from app.database import Product
from app.web.main import _apply_product_filters, _search_pattern


def test_search_pattern_lowercase_and_yo() -> None:
    """Паттерн приводит строку к нижнему регистру и заменяет букву ё."""
    assert _search_pattern("  E27 Ё  ") == "%e27 е%"


def test_product_filters_combine_name_norm_and_name_with_or() -> None:
    """При непустом запросе фильтр включает условие OR по name_norm и name."""
    stmt = _apply_product_filters(select(Product.id), q="лампа", shop="")
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "name_norm" in sql
    assert "products.name" in sql or "name " in sql
    assert " or " in sql


def test_product_filters_empty_query_adds_no_name_predicate() -> None:
    """Без текстового запроса не добавляются предикаты по наименованию."""
    stmt = _apply_product_filters(select(Product.id), q="", shop="")
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "name_norm" not in sql
