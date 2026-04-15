"""move evolution provider tables to whatsapp schema

Revision ID: 20260411_14
Revises: 20260411_13
Create Date: 2026-04-11 12:40:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260411_14"
down_revision: str | Sequence[str] | None = "20260411_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EVOLUTION_TABLES = [
    "Chat",
    "Chatwoot",
    "Contact",
    "Dify",
    "DifySetting",
    "EvolutionBot",
    "EvolutionBotSetting",
    "Flowise",
    "FlowiseSetting",
    "Instance",
    "IntegrationSession",
    "IsOnWhatsapp",
    "Label",
    "Media",
    "Message",
    "MessageUpdate",
    "OpenaiBot",
    "OpenaiCreds",
    "OpenaiSetting",
    "Proxy",
    "Pusher",
    "Rabbitmq",
    "Session",
    "Setting",
    "Sqs",
    "Template",
    "Typebot",
    "TypebotSetting",
    "Webhook",
    "Websocket",
    "_prisma_migrations",
]


def _move_tables(source_schema: str, target_schema: str) -> None:
    for table_name in EVOLUTION_TABLES:
        op.execute(
            f'ALTER TABLE IF EXISTS "{source_schema}"."{table_name}" SET SCHEMA "{target_schema}"'
        )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS whatsapp")
    _move_tables("public", "whatsapp")


def downgrade() -> None:
    _move_tables("whatsapp", "public")
