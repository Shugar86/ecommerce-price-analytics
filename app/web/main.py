"""
Веб-интерфейс для аналитика: дашборд, поиск, графики, аномалии, выгрузки.

Запуск: ``uvicorn app.web.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Generator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import Date, cast, func, or_, select, text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import quote_plus

from app.database import (
    PriceAnomaly,
    PriceForecast,
    PriceHistory,
    Product,
    ProductMatch,
    dispose_engine,
    get_engine,
    get_session,
    init_db,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_http_basic = HTTPBasic(auto_error=False)


def _search_pattern(q: str) -> str:
    """Паттерн ILIKE для поиска по наименованию (нормализованному и полному)."""
    return f"%{q.strip().lower().replace('ё', 'е')}%"


def _apply_product_filters(stmt, *, q: str, shop: str):
    """Добавляет фильтры по источнику и текстовому запросу к select-запросу по Product."""
    if shop.strip():
        stmt = stmt.where(Product.source_shop == shop.strip())
    if q.strip():
        pat = _search_pattern(q)
        stmt = stmt.where(
            or_(
                Product.name_norm.ilike(pat),
                Product.name.ilike(pat),
            )
        )
    return stmt


def get_db_session() -> Generator[Session, None, None]:
    """Выдаёт сессию БД на запрос (один пул Engine на процесс)."""
    engine = get_engine()
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


def require_web_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_http_basic)],
) -> None:
    """
    Опциональная Basic-аутентификация.

    Если заданы обе переменные ``WEB_BASIC_AUTH_USER`` и ``WEB_BASIC_AUTH_PASSWORD``,
    без корректных учётных данных доступ к защищённым маршрутам запрещён.
    """
    expected_user = (os.getenv("WEB_BASIC_AUTH_USER") or "").strip()
    expected_pass = (os.getenv("WEB_BASIC_AUTH_PASSWORD") or "").strip()
    if not expected_user or not expected_pass:
        return
    if (
        credentials is None
        or credentials.username != expected_user
        or credentials.password != expected_pass
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="analytics"'},
        )


SessionDep = Annotated[Session, Depends(get_db_session)]

router = APIRouter(dependencies=[Depends(require_web_auth)])


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Инициализация схемы БД при старте контейнера и освобождение пула при остановке."""
    try:
        engine = get_engine()
        init_db(engine)
    except Exception as exc:
        logger.warning("Стартовая инициализация БД: %s", exc)
    yield
    dispose_engine()


app = FastAPI(
    title="Аналитика цен e-commerce",
    description="Микросервисное веб-приложение визуального анализа цен",
    version="1.0.0",
    lifespan=_lifespan,
)
templates.env.filters["urlencode"] = quote_plus
app.include_router(router)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Минимальные заголовки безопасности для HTML/CSV ответов."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


app.add_middleware(_SecurityHeadersMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости сервиса (без обращения к БД)."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Готовность к трафику: проверка соединения с PostgreSQL."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        logger.warning("Readiness: база недоступна: %s", exc)
        raise HTTPException(status_code=503, detail="database_unavailable") from exc


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    """Главная страница: сводные метрики."""
    total = session.scalar(select(func.count(Product.id))) or 0
    shops = session.execute(
        select(Product.source_shop, func.count(Product.id))
        .group_by(Product.source_shop)
        .order_by(func.count(Product.id).desc())
    ).all()
    last_upd = session.scalar(select(func.max(Product.updated_at)))
    price_stats = session.execute(
        select(
            func.min(Product.price_in_rub),
            func.max(Product.price_in_rub),
            func.avg(Product.price_in_rub),
        )
    ).one()
    anomalies_n = session.scalar(select(func.count(PriceAnomaly.id))) or 0
    matches_n = session.scalar(select(func.count(ProductMatch.id))) or 0

    day_col = cast(PriceHistory.collected_at, Date)
    history_trend = session.execute(
        select(day_col, func.avg(PriceHistory.price_in_rub))
        .group_by(day_col)
        .order_by(day_col.desc())
        .limit(10)
    ).all()
    history_trend = list(reversed(history_trend))
    trend_labels = [r[0].isoformat() if r[0] else "" for r in history_trend]
    trend_values = [float(r[1] or 0) for r in history_trend]

    shop_labels = [s for s, _ in shops if s]
    shop_counts = [int(c) for s, c in shops if s]

    ctx = {
        "request": request,
        "total_products": int(total),
        "shops": [(s, int(c)) for s, c in shops if s],
        "last_update": last_upd,
        "price_min": float(price_stats[0] or 0),
        "price_max": float(price_stats[1] or 0),
        "price_avg": float(price_stats[2] or 0),
        "anomalies_n": int(anomalies_n),
        "matches_n": int(matches_n),
        "shop_labels_json": json.dumps(shop_labels, ensure_ascii=False),
        "shop_counts_json": json.dumps(shop_counts, ensure_ascii=False),
        "trend_labels_json": json.dumps(trend_labels, ensure_ascii=False),
        "trend_values_json": json.dumps(trend_values, ensure_ascii=False),
    }
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/products", response_class=HTMLResponse)
def products_list(
    request: Request,
    session: SessionDep,
    q: str = Query("", max_length=200),
    shop: str = Query("", max_length=100),
) -> HTMLResponse:
    """Список товаров с фильтрами."""
    count_stmt = _apply_product_filters(select(func.count(Product.id)), q=q, shop=shop)
    total_matching = int(session.scalar(count_stmt) or 0)

    list_stmt = _apply_product_filters(select(Product), q=q, shop=shop).order_by(Product.price_in_rub).limit(200)
    rows = session.execute(list_stmt).scalars().all()
    shops = session.execute(select(Product.source_shop).distinct().order_by(Product.source_shop)).scalars().all()

    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "products": rows,
            "shops": [s for s in shops if s],
            "q": q,
            "shop": shop,
            "total_matching": total_matching,
        },
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(
    request: Request,
    session: SessionDep,
    product_id: int,
) -> HTMLResponse:
    """Карточка товара, график истории, прогноз."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    hist_rows = session.execute(
        select(PriceHistory.price_in_rub, PriceHistory.collected_at)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.collected_at.asc())
    ).all()

    chart_labels = [r[1].strftime("%Y-%m-%d %H:%M") for r in hist_rows]
    chart_values = [float(r[0]) for r in hist_rows]

    anomalies = session.execute(
        select(PriceAnomaly)
        .where(PriceAnomaly.product_id == product_id)
        .order_by(PriceAnomaly.detected_at.desc())
    ).scalars().all()

    forecast = session.execute(
        select(PriceForecast)
        .where(PriceForecast.product_id == product_id)
        .order_by(PriceForecast.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    matches = session.execute(
        select(ProductMatch).where(
            (ProductMatch.product_low_id == product_id) | (ProductMatch.product_high_id == product_id)
        )
    ).scalars().all()
    other_ids: list[int] = []
    for m in matches:
        oid = m.product_high_id if m.product_low_id == product_id else m.product_low_id
        other_ids.append(int(oid))
    others: dict[int, Product] = {}
    for oid in other_ids[:20]:
        p = session.get(Product, oid)
        if p:
            others[oid] = p

    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "product": product,
            "chart_labels_json": json.dumps(chart_labels, ensure_ascii=False),
            "chart_values_json": json.dumps(chart_values, ensure_ascii=False),
            "anomalies": anomalies,
            "forecast": forecast,
            "matches": matches,
            "match_products": others,
        },
    )


@router.get("/anomalies", response_class=HTMLResponse)
def anomalies_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Таблица аномалий (результат ИИ-воркера)."""
    rows = session.execute(
        select(PriceAnomaly, Product)
        .join(Product, Product.id == PriceAnomaly.product_id)
        .order_by(PriceAnomaly.detected_at.desc())
        .limit(300)
    ).all()
    return templates.TemplateResponse(
        "anomalies.html",
        {"request": request, "rows": rows},
    )


@router.get("/matches", response_class=HTMLResponse)
def matches_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Сопоставления EKF↔TDM (TF-IDF)."""
    pairs = session.execute(
        select(ProductMatch).order_by(ProductMatch.score.desc()).limit(200)
    ).scalars().all()
    products: dict[int, Product] = {}
    for m in pairs:
        for pid in (m.product_low_id, m.product_high_id):
            if pid not in products:
                p = session.get(Product, pid)
                if p:
                    products[pid] = p
    return templates.TemplateResponse(
        "matches.html",
        {"request": request, "pairs": pairs, "products": products},
    )


@router.get("/export/products.csv")
def export_products_csv(
    session: SessionDep,
    q: str = Query("", max_length=200),
    shop: str = Query("", max_length=100),
) -> Response:
    """Выгрузка отфильтрованного списка товаров в CSV."""
    stmt = _apply_product_filters(
        select(Product).order_by(Product.source_shop, Product.name).limit(5000),
        q=q,
        shop=shop,
    )
    rows = session.execute(stmt).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        ["id", "external_id", "name", "price_in_rub", "currency", "source_shop", "url", "updated_at"]
    )
    for p in rows:
        writer.writerow(
            [
                p.id,
                p.external_id,
                p.name,
                f"{p.price_in_rub:.2f}",
                p.currency,
                p.source_shop,
                p.url or "",
                p.updated_at.isoformat() if p.updated_at else "",
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="products.csv"'},
    )


@router.get("/export/anomalies.csv")
def export_anomalies_csv(session: SessionDep) -> Response:
    """Выгрузка таблицы аномалий."""
    rows = session.execute(
        select(PriceAnomaly, Product)
        .join(Product, Product.id == PriceAnomaly.product_id)
        .order_by(PriceAnomaly.detected_at.desc())
        .limit(5000)
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        ["detected_at", "anomaly_type", "severity", "price", "product_id", "product_name", "detail"]
    )
    for a, p in rows:
        writer.writerow(
            [
                a.detected_at.isoformat(),
                a.anomaly_type,
                f"{a.severity:.4f}",
                f"{a.price_at_detection:.2f}",
                p.id,
                p.name,
                (a.detail or "").replace("\n", " "),
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="anomalies.csv"'},
    )
