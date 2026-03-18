import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.repositories.tenant import TenantRepository, PaymentRepository
from app.models.tenant import SubscriptionStatus


class PaymentService:
    """Single Responsibility: manage tenant payments and subscription logic."""

    def __init__(self, db: Session) -> None:
        self.payment_repo = PaymentRepository(db)
        self.tenant_repo = TenantRepository(db)

    def register_payment(self, tenant_id: uuid.UUID, *, amount, payment_method=None, reference_code=None):
        """
        Register payment for tenant.
        Rules:
        - Prevent duplicate via reference_code
        - Auto-extend subscription by 30 days
        """
        # Validate tenant exists
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        # Prevent duplicates
        if reference_code:
            existing = self.payment_repo.get_by_reference(reference_code)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment with this reference code already exists",
                )

        # Create payment
        payment = self.payment_repo.create(
            tenant_id=tenant_id,
            amount=amount,
            payment_method=payment_method,
            reference_code=reference_code,
        )

        # Extend subscription
        self.tenant_repo.extend_subscription(tenant_id, days=30)

        return payment

    def list_tenant_payments(self, tenant_id: uuid.UUID):
        """List payments for a tenant (multi-tenant enforced)."""
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return self.payment_repo.list_by_tenant(tenant_id)
