"""Barcode enrichment reference (e.g. Catalog.app dump).

Revision ID: 005_barcode_reference
Revises: 004_normalized_offer_matches
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "005_barcode_reference"
down_revision: Union[str, None] = "004_normalized_offer_matches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create barcode_reference for lookup by normalized barcode digits."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS barcode_reference (
            id SERIAL PRIMARY KEY,
            barcode VARCHAR(14) NOT NULL,
            category VARCHAR(500),
            vendor VARCHAR(300),
            name VARCHAR(500),
            article VARCHAR(128),
            source_batch VARCHAR(64),
            CONSTRAINT uq_barcode_reference_barcode UNIQUE (barcode)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_barcode_reference_barcode "
        "ON barcode_reference (barcode)"
    )


def downgrade() -> None:
    """Drop barcode reference table."""
    op.execute("DROP TABLE IF EXISTS barcode_reference")
