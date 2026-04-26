"""Source health: last error and fetch duration (Tier A telemetry).

Revision ID: 006_source_health_telemetry
Revises: 005_barcode_reference
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "006_source_health_telemetry"
down_revision: Union[str, None] = "005_barcode_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Idempotent: last_error, last_fetch_duration_sec on source_health."""
    op.execute(
        "ALTER TABLE source_health ADD COLUMN IF NOT EXISTS last_error VARCHAR(2000)"
    )
    op.execute(
        "ALTER TABLE source_health ADD COLUMN IF NOT EXISTS last_fetch_duration_sec "
        "DOUBLE PRECISION"
    )


def downgrade() -> None:
    """Drop telemetry columns."""
    op.execute("ALTER TABLE source_health DROP COLUMN IF EXISTS last_fetch_duration_sec")
    op.execute("ALTER TABLE source_health DROP COLUMN IF EXISTS last_error")
