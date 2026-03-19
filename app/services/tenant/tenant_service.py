import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.tenant import TenantRepository


class TenantService:
    """Single Responsibility: manage tenant business logic."""

    def __init__(self, db: Session) -> None:
        self.tenant_repo = TenantRepository(db)

    @staticmethod
    def _normalize_business_hours(business_hours: dict | None) -> dict | None:
        if business_hours is None:
            return None
        normalized: dict = {}
        for day, value in business_hours.items():
            if hasattr(value, "model_dump"):
                normalized[day] = value.model_dump()
            else:
                normalized[day] = value
        return normalized

    def create_tenant(
        self,
        *,
        name: str,
        phone: str | None,
        slot_duration: int = 15,
        max_users: int = 5,
        business_hours: dict | None = None,
    ):
        """Create new tenant with 30-day trial subscription."""
        return self.tenant_repo.create(
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            max_users=max_users,
            business_hours=self._normalize_business_hours(business_hours),
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
        max_users: int | None = None,
        business_hours: dict | None = None,
    ):
        """Update tenant settings."""
        tenant = self.tenant_repo.update(
            tenant_id,
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            max_users=max_users,
            business_hours=self._normalize_business_hours(business_hours),
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def update_owner_settings(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str | None = None,
        phone: str | None = None,
        slot_duration: int | None = None,
        business_hours: dict | None = None,
    ):
        tenant = self.tenant_repo.update(
            tenant_id,
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            business_hours=self._normalize_business_hours(business_hours),
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant
