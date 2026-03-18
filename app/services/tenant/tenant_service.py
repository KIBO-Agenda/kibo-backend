import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant import TenantRepository


class TenantService:
    """Single Responsibility: manage tenant business logic."""

    def __init__(self, db: Session) -> None:
        self.tenant_repo = TenantRepository(db)

    def create_tenant(self, *, name: str, phone: str | None, slot_duration: int = 15):
        """Create new tenant with 30-day trial subscription."""
        return self.tenant_repo.create(
            name=name, phone=phone, slot_duration=slot_duration
        )

    def get_tenant(self, tenant_id: uuid.UUID):
        """Get tenant by ID."""
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def list_tenants(self):
        """List all tenants (super_admin only)."""
        return self.tenant_repo.list_all()

    def update_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str | None = None,
        phone: str | None = None,
        slot_duration: int | None = None,
    ):
        """Update tenant settings."""
        tenant = self.tenant_repo.update(
            tenant_id, name=name, phone=phone, slot_duration=slot_duration
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant
