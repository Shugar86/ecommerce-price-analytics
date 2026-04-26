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

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import quote_plus

from app.database import (
    MATCH_STATUS_CONFIRMED,
    MATCH_STATUS_REJECTED,
    MATCH_STATUS_SUGGESTED,
    NormalizedOffer,
    NormalizedOfferMatch,
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
from app.analytics.price_intelligence import load_market_rows, our_pricing_source
from app.web.services import (
    build_dashboard_template_context,
    list_source_health_rows,
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
    title="PriceDesk — ценовая аналитика e-commerce",
    description=(
        "Мониторинг прайс-листов, история цен, эвристики аномалий и ассистированное сопоставление "
        "позиций по TF-IDF. Кандидаты сопоставления — подсказки для аналитика, не автоматическое "
        "объединение каталогов (см. docs/PRODUCT_SCOPE.md)."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)
templates.env.filters["urlencode"] = quote_plus


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
    ctx = build_dashboard_template_context(session)
    return templates.TemplateResponse(request, "dashboard.html", ctx)


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
        request,
        "products.html",
        {
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
        select(ProductMatch)
        .where(
            (ProductMatch.product_low_id == product_id)
            | (ProductMatch.product_high_id == product_id),
            ProductMatch.match_status != MATCH_STATUS_REJECTED,
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
        request,
        "product_detail.html",
        {
            "product": product,
            "chart_labels_json": json.dumps(chart_labels, ensure_ascii=False),
            "chart_values_json": json.dumps(chart_values, ensure_ascii=False),
            "anomalies": anomalies,
            "forecast": forecast,
            "matches": matches,
            "match_products": others,
        },
    )


@router.get("/anomalies", response_class=RedirectResponse)
def anomalies_alias() -> RedirectResponse:
    """Совместимость: /anomalies → /alerts."""
    return RedirectResponse(url="/alerts", status_code=307)


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Таблица ценовых алертов (аномалии; воркер эвристик)."""
    rows = session.execute(
        select(PriceAnomaly, Product)
        .join(Product, Product.id == PriceAnomaly.product_id)
        .order_by(PriceAnomaly.detected_at.desc())
        .limit(300)
    ).all()
    type_counts: dict[str, int] = {}
    for a, _ in rows:
        type_counts[a.anomaly_type] = type_counts.get(a.anomaly_type, 0) + 1
    return templates.TemplateResponse(
        request,
        "alerts.html",
        {"rows": rows, "type_counts": type_counts},
    )


@router.get("/market", response_class=HTMLResponse)
def market_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Таблица market position (canonical + KPI)."""
    rows = load_market_rows(
        session, limit=500, our_src=our_pricing_source()
    )
    return templates.TemplateResponse(
        request,
        "market.html",
        {
            "rows": rows,
            "our_pricing_source": our_pricing_source(),
        },
    )


@router.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Реестр источников и source_health."""
    sh_rows = list_source_health_rows(session)
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"sources": sh_rows},
    )


@router.get("/matches", response_class=HTMLResponse)
def matches_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Ассистент сопоставления: кандидаты по normalized_offers (TF-IDF) и legacy Product."""
    offer_pairs = session.execute(
        select(NormalizedOfferMatch).order_by(NormalizedOfferMatch.score.desc()).limit(200)
    ).scalars().all()
    offer_ids: set[int] = set()
    for m in offer_pairs:
        offer_ids.add(int(m.offer_low_id))
        offer_ids.add(int(m.offer_high_id))
    offers_map: dict[int, NormalizedOffer] = {}
    for oid in offer_ids:
        o = session.get(NormalizedOffer, oid)
        if o:
            offers_map[oid] = o

    offer_suggested_n = sum(
        1 for m in offer_pairs if m.match_status == MATCH_STATUS_SUGGESTED
    )
    offer_confirmed_n = sum(
        1 for m in offer_pairs if m.match_status == MATCH_STATUS_CONFIRMED
    )
    offer_rejected_n = sum(
        1 for m in offer_pairs if m.match_status == MATCH_STATUS_REJECTED
    )

    legacy_pairs = session.execute(
        select(ProductMatch).order_by(ProductMatch.score.desc()).limit(200)
    ).scalars().all()
    products: dict[int, Product] = {}
    for m in legacy_pairs:
        for pid in (m.product_low_id, m.product_high_id):
            if pid not in products:
                p = session.get(Product, pid)
                if p:
                    products[pid] = p
    legacy_suggested_n = sum(
        1 for m in legacy_pairs if m.match_status == MATCH_STATUS_SUGGESTED
    )
    legacy_confirmed_n = sum(
        1 for m in legacy_pairs if m.match_status == MATCH_STATUS_CONFIRMED
    )
    legacy_rejected_n = sum(
        1 for m in legacy_pairs if m.match_status == MATCH_STATUS_REJECTED
    )

    suggested_n = offer_suggested_n + legacy_suggested_n
    confirmed_n = offer_confirmed_n + legacy_confirmed_n
    rejected_n = offer_rejected_n + legacy_rejected_n

    return templates.TemplateResponse(
        request,
        "matches.html",
        {
            "offer_pairs": offer_pairs,
            "offers_map": offers_map,
            "offer_suggested_n": offer_suggested_n,
            "offer_confirmed_n": offer_confirmed_n,
            "offer_rejected_n": offer_rejected_n,
            "legacy_pairs": legacy_pairs,
            "products": products,
            "legacy_suggested_n": legacy_suggested_n,
            "legacy_confirmed_n": legacy_confirmed_n,
            "legacy_rejected_n": legacy_rejected_n,
            "suggested_n": suggested_n,
            "confirmed_n": confirmed_n,
            "rejected_n": rejected_n,
            "ai_match_left": os.getenv("AI_MATCH_NORMALIZED_LEFT", "EKF YML"),
            "ai_match_right": os.getenv("AI_MATCH_NORMALIZED_RIGHT", "TDM Electric"),
        },
    )


@router.post("/matches/{match_id}/status", response_class=RedirectResponse)
def set_match_status(
    session: SessionDep,
    match_id: int,
    status: str = Form(...),
) -> RedirectResponse:
    """Подтвердить или отклонить кандидат сопоставления Product (legacy)."""
    if status not in (MATCH_STATUS_CONFIRMED, MATCH_STATUS_REJECTED):
        raise HTTPException(status_code=400, detail="status must be confirmed or rejected")
    row = session.get(ProductMatch, match_id)
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row.match_status != MATCH_STATUS_SUGGESTED:
        raise HTTPException(status_code=400, detail="only suggested candidates can be reviewed")
    row.match_status = status
    session.commit()
    return RedirectResponse(url="/matches", status_code=303)


@router.post("/matches/offers/{match_id}/status", response_class=RedirectResponse)
def set_offer_match_status(
    session: SessionDep,
    match_id: int,
    status: str = Form(...),
) -> RedirectResponse:
    """Подтвердить или отклонить кандидат по normalized_offers."""
    if status not in (MATCH_STATUS_CONFIRMED, MATCH_STATUS_REJECTED):
        raise HTTPException(status_code=400, detail="status must be confirmed or rejected")
    row = session.get(NormalizedOfferMatch, match_id)
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row.match_status != MATCH_STATUS_SUGGESTED:
        raise HTTPException(status_code=400, detail="only suggested candidates can be reviewed")
    row.match_status = status
    session.commit()
    return RedirectResponse(url="/matches", status_code=303)


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


# Подключаем router после всех @router.get — иначе include_router срабатывает с пустым набором маршрутов.
app.include_router(router)
