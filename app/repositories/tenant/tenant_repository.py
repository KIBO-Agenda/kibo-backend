import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantRepository:
    """Single Responsibility: tenant data access only."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self, *, name: str, phone: str | None, slot_duration: int = 15
    ) -> Tenant:
        """Create new tenant with initial subscription (30 days from now)."""
        now = datetime.now(timezone.utc)
        tenant = Tenant(
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            subscription_valid_until=now + timedelta(days=30),
        )
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        """No multi-tenant filter needed: admin action returning own data."""
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self) -> list[Tenant]:
        """List all tenants (admin/super_admin only)."""
        stmt = select(Tenant).order_by(Tenant.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def update(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str | None = None,
        phone: str | None = None,
        slot_duration: int | None = None,
    ) -> Tenant | None:
        """Update tenant fields selectively."""
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return None

        if name is not None:
            tenant.name = name
        if phone is not None:
            tenant.phone = phone
        if slot_duration is not None:
            tenant.slot_duration = slot_duration

        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def extend_subscription(
        self, tenant_id: uuid.UUID, days: int = 30
    ) -> Tenant | None:
        """Extend subscription_valid_until by N days."""
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return None

        tenant.subscription_valid_until = tenant.subscription_valid_until + timedelta(
            days=days
        )
        self.db.commit()
        self.db.refresh(tenant)
        return tenant
