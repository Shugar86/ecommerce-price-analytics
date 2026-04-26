"""Idempotent patches and indexes for legacy databases.

Revision ID: 001_bootstrap
Revises:
Create Date: 2026-02-06

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001_bootstrap"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply IF NOT EXISTS DDL safe for fresh and upgraded DBs."""
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS barcode VARCHAR(128)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS vendor_code VARCHAR(128)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id VARCHAR(64)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS name_norm VARCHAR(600)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_barcode ON products (barcode)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_vendor_code ON products (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_source_shop ON products (source_shop)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_name_norm ON products (name_norm)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_history_product_collected "
        "ON price_history (product_id, collected_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_anomalies_detected ON price_anomalies (detected_at)"
    )


def downgrade() -> None:
    """No-op: idempotent bootstrap; dropping columns risks data loss."""
