"""create tenants and tenant_payments tables

Revision ID: 20260318_02
Revises: 20260318_01
Create Date: 2026-03-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260318_02"
down_revision: str | None = "20260318_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    subscription_status_enum = postgresql.ENUM(
        "active", "past_due", "suspended", name="subscription_status"
    )
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "subscription_status",
            postgresql.ENUM(
                "active", "past_due", "suspended", name="subscription_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'active'::subscription_status"),
        ),
        sa.Column("subscription_valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_duration", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tenant_payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "payment_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("payment_method", sa.String(length=100), nullable=True),
        sa.Column("reference_code", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_code"),
    )
    op.create_index("idx_payments_tenant", "tenant_payments", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_payments_tenant", table_name="tenant_payments")
    op.drop_table("tenant_payments")
    op.drop_table("tenants")

    subscription_status_enum = postgresql.ENUM(
        "active", "past_due", "suspended", name="subscription_status"
    )
    subscription_status_enum.drop(op.get_bind(), checkfirst=True)
