"""Normalized offer match queue (fuzzy review on normalized layer).

Revision ID: 004_normalized_offer_matches
Revises: 003_price_intelligence
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "004_normalized_offer_matches"
down_revision: Union[str, None] = "003_price_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create normalized_offer_matches for offer-level review (TF-IDF fuzzy)."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_offer_matches (
            id SERIAL PRIMARY KEY,
            offer_low_id INTEGER NOT NULL
                REFERENCES normalized_offers(id) ON DELETE CASCADE,
            offer_high_id INTEGER NOT NULL
                REFERENCES normalized_offers(id) ON DELETE CASCADE,
            score DOUBLE PRECISION NOT NULL,
            method VARCHAR(64) NOT NULL,
            match_kind VARCHAR(32) NOT NULL DEFAULT 'fuzzy_tfidf',
            match_status VARCHAR(32) NOT NULL DEFAULT 'suggested',
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
            CONSTRAINT uq_normalized_offer_matches_pair
                UNIQUE (offer_low_id, offer_high_id),
            CONSTRAINT ck_normalized_offer_matches_order
                CHECK (offer_low_id < offer_high_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_norm_offer_matches_status "
        "ON normalized_offer_matches (match_status, match_kind)"
    )


def downgrade() -> None:
    """Drop normalized offer match table."""
    op.execute("DROP TABLE IF EXISTS normalized_offer_matches")
