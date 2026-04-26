"""OWWA (Tier C) — хранение внешних ритейл-наблюдений цен.

Revision ID: 007_owwa_listings
Revises: 006_source_health_telemetry
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "007_owwa_listings"
down_revision: Union[str, None] = "006_source_health_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create owwa_listings (опциональные снимки цен; не B2B normalized_offers)."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owwa_listings (
            id SERIAL PRIMARY KEY,
            platform_label VARCHAR(80) NOT NULL,
            product_url VARCHAR(2000) NOT NULL,
            title VARCHAR(500),
            price_rub DOUBLE PRECISION,
            currency_id VARCHAR(10),
            external_item_id VARCHAR(200),
            collected_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
            raw_json TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_owwa_listings_url "
        "ON owwa_listings (product_url)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_owwa_listings_platform "
        "ON owwa_listings (platform_label)"
    )


def downgrade() -> None:
    """Drop OWWA table."""
    op.execute("DROP TABLE IF EXISTS owwa_listings")
