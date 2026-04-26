"""ETL адаптеры для нормализованного слоя (офферы, source_health)."""

from app.collectors.complect_service import COMPLECT_URLS, fetch_complect_offers
from app.collectors.syperopt import SYPEROPT_XLSX_URL, fetch_syperopt_offers

__all__ = [
    "COMPLECT_URLS",
    "SYPEROPT_XLSX_URL",
    "fetch_complect_offers",
    "fetch_syperopt_offers",
]
