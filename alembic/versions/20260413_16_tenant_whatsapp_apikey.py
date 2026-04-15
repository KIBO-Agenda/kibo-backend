"""add tenant whatsapp apikey column

Revision ID: 20260413_16
Revises: 20260411_15
Create Date: 2026-04-13 10:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260413_16"
down_revision: str | Sequence[str] | None = "20260411_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("whatsapp_apikey", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "whatsapp_apikey")
