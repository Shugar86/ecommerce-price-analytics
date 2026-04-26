"""
Скачивание источников и отчёт source_audit.csv (покрытие полей, usable_score).

Запуск: ``python -m app.tools.source_audit`` из корня репозитория.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

import requests
import xlrd
from lxml import etree

from app.collectors.health_stats import coverage_from_rows
from app.collectors.syperopt import SYPEROPT_XLSX_URL, iter_syperopt_rows
from app.collectors.xls_common import iter_xls_tdm_rows
from app.collector import EKF_YML_URL, TDM_PRICE_XLS_URL  # noqa: PLC2401
from app.collectors.complect_service import COMPLECT_SERVICE_SOURCES, _complect_rows

logger = logging.getLogger(__name__)

# Syperopt: публичный API iter — для аудита дублируем загрузку.
from openpyxl import load_workbook  # noqa: E402

AUDIT_DEFAULT_OUT = "source_audit.csv"

SOURCES: list[tuple[str, str, str]] = [
    ("EKF YML", "yml", EKF_YML_URL),
    ("TDM XLS", "xls", TDM_PRICE_XLS_URL),
    ("Syperopt", "xlsx", SYPEROPT_XLSX_URL),
] + [
    (display, f"xls-complect:{key}", url)
    for key, (display, url) in COMPLECT_SERVICE_SOURCES.items()
]


def _rows_ekf_yml(url: str) -> list[dict[str, Any]]:
    from app.collector import (  # noqa: PLC2401
        _ekf_row_from_offer,
        _clear_parsed_offer,
        _fetch_yml_stream,
    )

    rows: list[dict[str, Any]] = []
    response = _fetch_yml_stream(url, timeout=(10, 180))
    context = etree.iterparse(
        response.raw,
        events=("end",),
        tag="offer",
        recover=True,
        huge_tree=True,
    )
    for _, offer_elem in context:
        oid = offer_elem.get("id")
        if not oid:
            _clear_parsed_offer(offer_elem)
            continue
        r = _ekf_row_from_offer(offer_elem, str(oid))
        _clear_parsed_offer(offer_elem)
        if not r:
            continue
        rows.append(
            {
                "price_rub": r["price_in_rub"],
                "vendor_code": r.get("vendor_code"),
                "barcode": r.get("barcode"),
                "brand": None,
                "name": r.get("name"),
            }
        )
    del context
    return rows


def _rows_tdm_xls(url: str) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    book = xlrd.open_workbook(file_contents=response.content)
    sheet = book.sheet_by_index(0)
    return list(iter_xls_tdm_rows(sheet))


def _rows_xlsx_syperopt(url: str) -> list[dict[str, Any]]:
    response = requests.get(
        url,
        timeout=600,
        headers={"User-Agent": "PriceDesk-SourceAudit/1.0"},
    )
    response.raise_for_status()
    wb = load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            return []
        return iter_syperopt_rows(ws)
    finally:
        wb.close()


def _rows_complect_xls(url: str, key: str) -> list[dict[str, Any]]:
    response = requests.get(
        url,
        timeout=300,
        headers={"User-Agent": "PriceDesk-SourceAudit/1.0"},
    )
    response.raise_for_status()
    book = xlrd.open_workbook(file_contents=response.content)
    sheet = book.sheet_by_index(0)
    return _complect_rows(sheet, key)


def audit_all(out_path: Path) -> int:
    """
    Пишет CSV и возвращает число обработанных источников.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "url",
                "rows",
                "price_pct",
                "vendor_code_pct",
                "barcode_pct",
                "brand_pct",
                "usable_score",
            ]
        )
        for name, kind, url in SOURCES:
            try:
                if kind.startswith("xls-complect:"):
                    ckey = kind.split(":", 1)[1]
                    rows = _rows_complect_xls(url, ckey)
                elif kind == "yml":
                    rows = _rows_ekf_yml(url)
                elif kind == "xls" and "TDM" in name:
                    rows = _rows_tdm_xls(url)
                elif kind == "xlsx":
                    rows = _rows_xlsx_syperopt(url)
                else:
                    continue
                cov = coverage_from_rows(rows)
                w.writerow(
                    [
                        name,
                        url,
                        cov.rows,
                        cov.price_pct,
                        cov.vendor_code_pct,
                        cov.barcode_pct,
                        cov.brand_pct,
                        f"{cov.usable_score:.4f}" if rows else "0.0000",
                    ]
                )
                n_ok += 1
            except (OSError, ValueError) as e:
                logger.warning("audit skip %s: %s", name, e)
                w.writerow([name, url, 0, 0, 0, 0, 0, "0.0000"])
    return n_ok


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    out = Path(os.environ.get("SOURCE_AUDIT_OUT", AUDIT_DEFAULT_OUT))
    n = audit_all(out)
    print(f"Wrote {out} ({n} sources OK)", file=sys.stderr)


if __name__ == "__main__":
    main()
