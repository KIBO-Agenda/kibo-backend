"""move evolution enum types to whatsapp schema

Revision ID: 20260411_15
Revises: 20260411_14
Create Date: 2026-04-11 13:15:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260411_15"
down_revision: str | Sequence[str] | None = "20260411_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EVOLUTION_ENUMS = [
    "DeviceMessage",
    "DifyBotType",
    "InstanceConnectionStatus",
    "OpenaiBotType",
    "SessionStatus",
    "TriggerOperator",
    "TriggerType",
]


def _move_enums(source_schema: str, target_schema: str) -> None:
    for enum_name in EVOLUTION_ENUMS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE n.nspname = '{source_schema}'
                      AND t.typname = '{enum_name}'
                      AND t.typtype = 'e'
                ) THEN
                    EXECUTE 'ALTER TYPE "{source_schema}"."{enum_name}" SET SCHEMA "{target_schema}"';
                END IF;
            END $$;
            """
        )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS whatsapp")
    _move_enums("public", "whatsapp")


def downgrade() -> None:
    _move_enums("whatsapp", "public")
