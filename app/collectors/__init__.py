"""ETL адаптеры для нормализованного слоя (офферы, source_health)."""

from app.collectors.complect_service import (
    COMPLECT_SERVICE_SOURCES,
    COMPLECT_SERVICE_SOURCE_KEYS,
    COMPLECT_URLS,
    fetch_all_complect_service,
    fetch_complect_offers,
    fetch_complect_service_offers,
)
from app.collectors.syperopt import SYPEROPT_XLSX_URL, fetch_syperopt_offers

__all__ = [
    "COMPLECT_SERVICE_SOURCES",
    "COMPLECT_SERVICE_SOURCE_KEYS",
    "COMPLECT_URLS",
    "SYPEROPT_XLSX_URL",
    "fetch_all_complect_service",
    "fetch_complect_offers",
    "fetch_complect_service_offers",
    "fetch_syperopt_offers",
]
