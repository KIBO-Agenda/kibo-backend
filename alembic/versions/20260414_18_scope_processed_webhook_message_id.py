"""scope processed_webhooks message id by tenant

Revision ID: 20260414_18
Revises: 20260414_17
Create Date: 2026-04-14 19:05:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260414_18"
down_revision: str | Sequence[str] | None = "20260414_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE whatsapp.processed_webhooks
        SET message_id = tenant_id::text || ':' || message_id
        WHERE message_id NOT LIKE tenant_id::text || ':%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE whatsapp.processed_webhooks
        SET message_id = split_part(message_id, ':', 2)
        WHERE message_id LIKE '%:%'
        """
    )
