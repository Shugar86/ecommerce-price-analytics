"""Smoke-тесты отчёта source_audit без сети."""

from __future__ import annotations

import csv
from pathlib import Path

from app.tools import source_audit as sa


def test_audit_all_with_monkeypatched_rows(tmp_path: Path, monkeypatch) -> None:
    """Пишет CSV и строку с ожидаемым источником при подмене загрузчика."""

    def fake_rows(*_a: object, **_kw: object) -> list[dict]:
        return [
            {
                "price_rub": 10.0,
                "vendor_code": "V1",
                "barcode": "1234567890123",
                "brand": "BR",
                "name": "Item",
            }
        ] * 5

    monkeypatch.setattr(sa, "SOURCES", [("TestYML", "yml", "http://example.invalid/yml")])
    monkeypatch.setattr(sa, "_rows_ekf_yml", fake_rows)
    out = tmp_path / "audit.csv"
    n = sa.audit_all(out)
    assert n >= 1
    with out.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        row = next(reader)
    assert "source" in header[0].lower() or header[0] == "source"
    assert row[0] == "TestYML"
    assert row[1] == "http://example.invalid/yml"
    assert int(row[2]) == 5
