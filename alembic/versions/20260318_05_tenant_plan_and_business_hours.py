"""add tenant max_users and business_hours

Revision ID: 20260318_05
Revises: 20260318_04
Create Date: 2026-03-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260318_05"
down_revision: str | None = "20260318_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_BUSINESS_HOURS_JSON = (
    "'{\"monday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"tuesday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"wednesday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"thursday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"friday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"saturday\": {\"is_open\": true, \"open\": \"08:00\", \"close\": \"18:00\"}, "
    "\"sunday\": {\"is_open\": false, \"open\": \"08:00\", \"close\": \"18:00\"}}'::jsonb"
)


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("max_users", sa.Integer(), nullable=False, server_default=sa.text("5")),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "business_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(DEFAULT_BUSINESS_HOURS_JSON),
        ),
    )

    # Normalize defaults for future inserts at DB level.
    op.alter_column("tenants", "max_users", server_default=sa.text("5"))
    op.alter_column(
        "tenants",
        "business_hours",
        server_default=sa.text(DEFAULT_BUSINESS_HOURS_JSON),
    )


def downgrade() -> None:
    op.drop_column("tenants", "business_hours")
    op.drop_column("tenants", "max_users")
