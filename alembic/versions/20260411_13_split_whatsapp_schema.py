"""split whatsapp tables into whatsapp schema

Revision ID: 20260411_13
Revises: a9fdbd1d5b46
Create Date: 2026-04-11 10:10:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260411_13"
down_revision: str | Sequence[str] | None = "a9fdbd1d5b46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS whatsapp")

    op.execute("ALTER TABLE IF EXISTS processed_webhooks SET SCHEMA whatsapp")
    op.execute("ALTER TABLE IF EXISTS conversation_contexts SET SCHEMA whatsapp")
    op.execute("ALTER TABLE IF EXISTS whatsapp_sessions SET SCHEMA whatsapp")
    op.execute("ALTER TABLE IF EXISTS whatsapp_outbox SET SCHEMA whatsapp")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS whatsapp.whatsapp_outbox SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS whatsapp.whatsapp_sessions SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS whatsapp.conversation_contexts SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS whatsapp.processed_webhooks SET SCHEMA public")
    op.execute("DROP SCHEMA IF EXISTS whatsapp")
