"""Add normalized offers, canonical products, source health for price intelligence.

Revision ID: 003_price_intelligence
Revises: 002_match_governance
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_price_intelligence"
down_revision: Union[str, None] = "002_match_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create price intelligence layer tables; keep legacy products intact."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_products (
            id SERIAL PRIMARY KEY,
            canonical_name VARCHAR(500),
            brand VARCHAR(200),
            vendor_code VARCHAR(128),
            barcode VARCHAR(128),
            category VARCHAR(200),
            match_confidence FLOAT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_canonical_vendor_brand "
        "ON canonical_products (vendor_code, brand)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_canonical_barcode "
        "ON canonical_products (barcode)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health (
            id SERIAL PRIMARY KEY,
            source_name VARCHAR(100) NOT NULL UNIQUE,
            last_loaded_at TIMESTAMP WITHOUT TIME ZONE,
            total_rows INTEGER,
            price_pct FLOAT,
            vendor_code_pct FLOAT,
            barcode_pct FLOAT,
            brand_pct FLOAT,
            usable_score FLOAT,
            source_url VARCHAR(500),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_offers (
            id SERIAL PRIMARY KEY,
            source_name VARCHAR(100) NOT NULL,
            source_url VARCHAR(500),
            external_id VARCHAR(255),
            name VARCHAR(500),
            brand VARCHAR(200),
            vendor_code VARCHAR(128),
            barcode VARCHAR(128),
            category VARCHAR(200),
            price_rub DOUBLE PRECISION,
            availability BOOLEAN,
            url VARCHAR(1000),
            loaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
            canonical_product_id INTEGER
                REFERENCES canonical_products(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_norm_offers_source "
        "ON normalized_offers (source_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_norm_offers_barcode "
        "ON normalized_offers (barcode)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_norm_offers_vendor_brand "
        "ON normalized_offers (vendor_code, brand)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_norm_offers_canonical "
        "ON normalized_offers (canonical_product_id)"
    )


def downgrade() -> None:
    """Drop new tables; order respects FKs."""
    op.execute("DROP TABLE IF EXISTS normalized_offers")
    op.execute("DROP TABLE IF EXISTS source_health")
    op.execute("DROP TABLE IF EXISTS canonical_products")
