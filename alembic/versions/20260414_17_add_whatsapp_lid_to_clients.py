"""add whatsapp_lid to clients

Revision ID: 20260414_17
Revises: 20260413_16
Create Date: 2026-04-14 08:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260414_17"
down_revision: str | Sequence[str] | None = "20260413_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("whatsapp_lid", sa.String(length=255), nullable=True))
    op.create_index(
        "idx_clients_tenant_whatsapp_lid",
        "clients",
        ["tenant_id", "whatsapp_lid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_clients_tenant_whatsapp_lid", table_name="clients")
    op.drop_column("clients", "whatsapp_lid")
