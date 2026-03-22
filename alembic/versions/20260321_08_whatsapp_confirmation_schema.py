"""whatsapp_confirmation_schema

Revision ID: 20260321_08
Revises: 20260320_07
Create Date: 2026-03-21 13:58:26.388820

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260321_08"
down_revision: str | None = "20260320_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("whatsapp_instance_id", sa.String(length=255), nullable=True))

    op.add_column("appointments", sa.Column("appointment_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("confirmation_status", sa.String(length=30), server_default=sa.text("'pending'"), nullable=False),
    )
    op.add_column(
        "appointments",
        sa.Column("reminder_24h_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "appointments",
        sa.Column("reminder_2h_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.execute(
        """
        UPDATE appointments
        SET appointment_time = (appointment_date::timestamp + time_start)
        WHERE appointment_time IS NULL
        """
    )

    op.create_index("idx_appointments_tenant_time", "appointments", ["tenant_id", "appointment_time"], unique=False)
    op.create_index("idx_clients_phone", "clients", ["phone"], unique=False)

    op.create_table(
        "conversation_contexts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_phone", sa.String(length=30), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_type", sa.String(length=50), nullable=False),
        sa.Column("context_token", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_conversation_contexts_client_phone",
        "conversation_contexts",
        ["client_phone"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_contexts_context_token",
        "conversation_contexts",
        ["context_token"],
        unique=True,
    )
    op.create_index("idx_conversation_contexts_tenant", "conversation_contexts", ["tenant_id"], unique=False)

    op.create_table(
        "whatsapp_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instance_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('connected', 'disconnected', 'connecting', 'qr_required')",
            name="ck_whatsapp_sessions_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_whatsapp_sessions_tenant", "whatsapp_sessions", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_whatsapp_sessions_tenant", table_name="whatsapp_sessions")
    op.drop_table("whatsapp_sessions")

    op.drop_index("idx_conversation_contexts_tenant", table_name="conversation_contexts")
    op.drop_index("idx_conversation_contexts_context_token", table_name="conversation_contexts")
    op.drop_index("idx_conversation_contexts_client_phone", table_name="conversation_contexts")
    op.drop_table("conversation_contexts")

    op.drop_index("idx_clients_phone", table_name="clients")
    op.drop_index("idx_appointments_tenant_time", table_name="appointments")
    op.drop_column("appointments", "reminder_2h_sent")
    op.drop_column("appointments", "reminder_24h_sent")
    op.drop_column("appointments", "confirmation_status")
    op.drop_column("appointments", "appointment_time")

    op.drop_column("tenants", "whatsapp_instance_id")
