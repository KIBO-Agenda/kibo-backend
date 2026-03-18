"""create clients, services and appointments tables

Revision ID: 20260318_03
Revises: 20260318_02
Create Date: 2026-03-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260318_03"
down_revision: str | None = "20260318_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    appointment_status_enum = postgresql.ENUM(
        "pending", "confirmed", "attended", "cancelled", name="appointment_status"
    )
    appointment_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "phone", name="idx_clients_tenant_phone_unique"),
    )
    op.create_index("idx_clients_tenant", "clients", ["tenant_id"], unique=False)

    op.create_table(
        "services",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_services_tenant", "services", ["tenant_id"], unique=False)

    op.create_table(
        "appointments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_date", sa.Date(), nullable=False),
        sa.Column("time_start", sa.Time(), nullable=False),
        sa.Column("time_end", sa.Time(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "confirmed",
                "attended",
                "cancelled",
                name="appointment_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'::appointment_status"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_appointments_tenant", "appointments", ["tenant_id"], unique=False)
    op.create_index("idx_appointments_date", "appointments", ["appointment_date"], unique=False)
    op.create_index(
        "idx_appointments_tenant_date",
        "appointments",
        ["tenant_id", "appointment_date"],
        unique=False,
    )
    op.create_index(
        "idx_prevent_overlap",
        "appointments",
        ["user_id", "appointment_date", "time_start", "time_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_prevent_overlap", table_name="appointments")
    op.drop_index("idx_appointments_tenant_date", table_name="appointments")
    op.drop_index("idx_appointments_date", table_name="appointments")
    op.drop_index("idx_appointments_tenant", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("idx_services_tenant", table_name="services")
    op.drop_table("services")

    op.drop_index("idx_clients_tenant", table_name="clients")
    op.drop_table("clients")

    appointment_status_enum = postgresql.ENUM(
        "pending", "confirmed", "attended", "cancelled", name="appointment_status"
    )
    appointment_status_enum.drop(op.get_bind(), checkfirst=True)
