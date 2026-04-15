"""timezone_templates_optout

Revision ID: 20260322_09
Revises: 20260321_08
Create Date: 2026-03-22 09:10:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260322_09"
down_revision: str | None = "20260321_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_MESSAGE_TEMPLATES_SQL = """
'{
  "reminder_24h": {
    "enabled": true,
    "variants": [
      "Hola {nombre}, recordatorio de tu cita manana en {negocio} a las {hora}."
    ]
  },
  "reminder_2h": {
    "enabled": true,
    "variants": [
      "Hola {nombre}, te esperamos hoy en {negocio} a las {hora}."
    ]
  },
  "welcome_message": {
    "enabled": true,
    "variants": [
      "Hola {nombre}, gracias por agendar en {negocio}."
    ]
  },
  "waitlist_notification": {
    "enabled": true,
    "variants": [
      "Hola {nombre}, se libero un cupo a las {hora_disponible}. Responde SI para continuar."
    ]
  }
}'::jsonb
"""


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("timezone_identifier", sa.String(length=64), server_default=sa.text("'America/Bogota'"), nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("message_templates", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text(DEFAULT_MESSAGE_TEMPLATES_SQL), nullable=False),
    )

    op.add_column(
        "clients",
        sa.Column("whatsapp_opt_out", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "clients",
        sa.Column("whatsapp_opt_out_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "whatsapp_opt_out_at")
    op.drop_column("clients", "whatsapp_opt_out")
    op.drop_column("tenants", "message_templates")
    op.drop_column("tenants", "timezone_identifier")
