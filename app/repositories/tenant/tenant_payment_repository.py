import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.tenant import TenantPayment


class PaymentRepository:
    """Single Responsibility: payment data access only."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: uuid.UUID,
        amount: Decimal,
        payment_method: str | None = None,
        reference_code: str | None = None,
    ) -> TenantPayment:
        """Create payment record for a tenant."""
        payment = TenantPayment(
            tenant_id=tenant_id,
            amount=amount,
            payment_method=payment_method,
            reference_code=reference_code,
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def get_by_id(self, payment_id: uuid.UUID) -> TenantPayment | None:
        """Get payment by ID."""
        stmt = select(TenantPayment).where(TenantPayment.id == payment_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID) -> list[TenantPayment]:
        """List payments for a specific tenant (multi-tenant filter)."""
        stmt = (
            select(TenantPayment)
            .where(TenantPayment.tenant_id == tenant_id)
            .order_by(TenantPayment.payment_date.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_reference(self, reference_code: str) -> TenantPayment | None:
        """Prevent duplicate payments via unique reference code."""
        stmt = select(TenantPayment).where(TenantPayment.reference_code == reference_code)
        return self.db.execute(stmt).scalar_one_or_none()

    def has_any_by_tenant(self, tenant_id: uuid.UUID) -> bool:
        stmt = select(func.count(TenantPayment.id)).where(TenantPayment.tenant_id == tenant_id)
        return int(self.db.execute(stmt).scalar_one() or 0) > 0
