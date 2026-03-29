"""whatsapp_remote_id_fields

Revision ID: a9fdbd1d5b46
Revises: 20260326_12
Create Date: 2026-03-28 21:34:19.993668

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9fdbd1d5b46"
down_revision: str | Sequence[str] | None = "20260326_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("whatsapp_remote_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "idx_appointments_whatsapp_remote_id",
        "appointments",
        ["whatsapp_remote_id"],
        postgresql_where=sa.text("whatsapp_remote_id IS NOT NULL"),
    )

    op.add_column(
        "processed_webhooks",
        sa.Column("remote_jid", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "idx_processed_webhooks_remote_jid",
        "processed_webhooks",
        ["tenant_id", "remote_jid"],
        unique=False,
        postgresql_where=sa.text("remote_jid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_processed_webhooks_remote_jid", table_name="processed_webhooks")
    op.drop_column("processed_webhooks", "remote_jid")

    op.drop_index("idx_appointments_whatsapp_remote_id", table_name="appointments")
    op.drop_column("appointments", "whatsapp_remote_id")
