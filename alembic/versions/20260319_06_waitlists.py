"""create waitlists table

Revision ID: 20260319_06
Revises: 20260318_05
Create Date: 2026-03-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260319_06"
down_revision: str | None = "20260318_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waitlists",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("client_phone", sa.String(length=30), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_waitlists_tenant", "waitlists", ["tenant_id"], unique=False)
    op.create_index("idx_waitlists_target_date", "waitlists", ["target_date"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_waitlists_target_date", table_name="waitlists")
    op.drop_index("idx_waitlists_tenant", table_name="waitlists")
    op.drop_table("waitlists")
