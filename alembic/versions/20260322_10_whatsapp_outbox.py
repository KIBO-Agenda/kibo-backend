"""whatsapp_outbox

Revision ID: 20260322_10
Revises: 20260322_09
Create Date: 2026-03-22 09:18:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260322_10"
down_revision: str | None = "20260322_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("template_variant_index", sa.Integer(), nullable=True),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("jitter_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'blocked_opt_out')",
            name="ck_whatsapp_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_whatsapp_outbox_attempts_non_negative"),
        sa.CheckConstraint("jitter_seconds >= 0", name="ck_whatsapp_outbox_jitter_non_negative"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_whatsapp_outbox_idempotency_key"),
    )

    op.create_index(
        "idx_whatsapp_outbox_status_next_attempt",
        "whatsapp_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "idx_whatsapp_outbox_business_created",
        "whatsapp_outbox",
        ["business_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_whatsapp_outbox_business_created", table_name="whatsapp_outbox")
    op.drop_index("idx_whatsapp_outbox_status_next_attempt", table_name="whatsapp_outbox")
    op.drop_table("whatsapp_outbox")
