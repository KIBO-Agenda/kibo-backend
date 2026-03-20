"""add trial_ends_at to tenants

Revision ID: 20260320_07
Revises: 20260319_06
Create Date: 2026-03-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260320_07"
down_revision: str | None = "20260319_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE tenants
        SET trial_ends_at = COALESCE(subscription_valid_until, now() + interval '15 days')
        """
    )

    op.alter_column("tenants", "trial_ends_at", nullable=False)


def downgrade() -> None:
    op.drop_column("tenants", "trial_ends_at")
