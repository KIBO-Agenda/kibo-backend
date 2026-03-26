"""webhook_idempotency_and_status

Revision ID: 20260326_12
Revises: 20260322_11
Create Date: 2026-03-26 14:35:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260326_12"
down_revision: str | None = "20260322_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'reschedule_req'")

    op.add_column(
        "appointments",
        sa.Column("last_notification_type", sa.String(length=20), nullable=False, server_default=sa.text("'none'")),
    )

    op.create_table(
        "processed_webhooks",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_phone", sa.String(length=30), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )

    op.create_table(
        "tenant_configs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("waitlist_manual_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    op.execute(
        """
        INSERT INTO tenant_configs (tenant_id, waitlist_manual_approval, whatsapp_enabled)
        SELECT id,
               COALESCE((message_templates ->> 'waitlist_manual_approval')::boolean, true),
               true
        FROM tenants
        ON CONFLICT (tenant_id) DO NOTHING
        """
    )

    op.add_column(
        "waitlists",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("waitlists", "service_id")
    op.drop_table("tenant_configs")
    op.drop_table("processed_webhooks")
    op.drop_column("appointments", "last_notification_type")
