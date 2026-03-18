"""make clients.phone nullable for implicit client creation

Revision ID: 20260318_04
Revises: 20260318_03
Create Date: 2026-03-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260318_04"
down_revision: str | None = "20260318_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("clients", "phone", existing_type=sa.String(length=30), nullable=True)


def downgrade() -> None:
    op.alter_column("clients", "phone", existing_type=sa.String(length=30), nullable=False)
