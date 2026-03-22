import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.tenant import PlanTier
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

    @staticmethod
    def _normalize_message_templates(message_templates: dict | None) -> dict | None:
        if message_templates is None:
            return None
        if hasattr(message_templates, "model_dump"):
            return message_templates.model_dump()
        return message_templates

    def create_tenant(
        self,
        *,
        name: str,
        phone: str | None,
        slot_duration: int = 15,
        max_users: int = 5,
        plan_tier: PlanTier = PlanTier.STARTER,
        timezone_identifier: str = "America/Bogota",
        business_hours: dict | None = None,
        message_templates: dict | None = None,
    ):
        """Create new tenant with 30-day trial subscription."""
        return self.tenant_repo.create(
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            max_users=max_users,
            plan_tier=plan_tier,
            timezone_identifier=timezone_identifier,
            business_hours=self._normalize_business_hours(business_hours),
            message_templates=self._normalize_message_templates(message_templates),
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
        plan_tier: PlanTier | None = None,
        timezone_identifier: str | None = None,
        business_hours: dict | None = None,
        message_templates: dict | None = None,
    ):
        """Update tenant settings."""
        tenant = self.tenant_repo.update(
            tenant_id,
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            max_users=max_users,
            plan_tier=plan_tier,
            timezone_identifier=timezone_identifier,
            business_hours=self._normalize_business_hours(business_hours),
            message_templates=self._normalize_message_templates(message_templates),
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
        timezone_identifier: str | None = None,
        business_hours: dict | None = None,
        message_templates: dict | None = None,
    ):
        tenant = self.tenant_repo.update(
            tenant_id,
            name=name,
            phone=phone,
            slot_duration=slot_duration,
            timezone_identifier=timezone_identifier,
            business_hours=self._normalize_business_hours(business_hours),
            message_templates=self._normalize_message_templates(message_templates),
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def get_owner_settings(self, tenant_id: uuid.UUID):
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant
