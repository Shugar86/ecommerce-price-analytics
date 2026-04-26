"""Add match_kind and match_status to product_matches (governance tier).

Revision ID: 002_match_governance
Revises: 001_bootstrap
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002_match_governance"
down_revision: Union[str, None] = "001_bootstrap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Idempotent: add columns for candidacy vs review workflow."""
    op.execute(
        "ALTER TABLE product_matches ADD COLUMN IF NOT EXISTS match_kind "
        "VARCHAR(32) NOT NULL DEFAULT 'fuzzy_tfidf'"
    )
    op.execute(
        "ALTER TABLE product_matches ADD COLUMN IF NOT EXISTS match_status "
        "VARCHAR(32) NOT NULL DEFAULT 'suggested'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_matches_status_kind "
        "ON product_matches (match_status, match_kind)"
    )


def downgrade() -> None:
    """Drop governance columns; safe for rollback only when acceptable."""
    op.execute("DROP INDEX IF EXISTS ix_product_matches_status_kind")
    op.execute("ALTER TABLE product_matches DROP COLUMN IF EXISTS match_status")
    op.execute("ALTER TABLE product_matches DROP COLUMN IF EXISTS match_kind")
