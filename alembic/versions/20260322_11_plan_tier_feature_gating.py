"""add_plan_tier_feature_gating

Revision ID: 20260322_11
Revises: 20260322_10
Create Date: 2026-03-22 12:20:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260322_11"
down_revision: str | None = "20260322_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PLAN_TIER_ENUM = sa.Enum("starter", "pro", "business", name="plan_tier")


def upgrade() -> None:
    bind = op.get_bind()
    PLAN_TIER_ENUM.create(bind, checkfirst=True)

    op.add_column(
        "tenants",
        sa.Column(
            "plan_tier",
            PLAN_TIER_ENUM,
            nullable=False,
            server_default=sa.text("'starter'"),
        ),
    )

    op.execute("UPDATE tenants SET plan_tier = 'starter' WHERE plan_tier IS NULL")
    op.execute("UPDATE tenants SET max_users = 2")


def downgrade() -> None:
    op.drop_column("tenants", "plan_tier")
    bind = op.get_bind()
    PLAN_TIER_ENUM.drop(bind, checkfirst=True)
