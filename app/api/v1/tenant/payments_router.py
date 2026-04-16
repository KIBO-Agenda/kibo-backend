import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_tenant_id_from_token
from app.db.session import get_db
from app.schemas.tenant import PaymentCreate, PaymentResponse
from app.services.tenant import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", status_code=status.HTTP_201_CREATED)
def register_payment(
    payload: PaymentCreate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """Register payment for tenant (owner only)."""
    tenant_id = uuid.UUID(tenant_id_str)

    service = PaymentService(db)
    payment = service.register_payment(
        tenant_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        reference_code=payload.reference_code,
    )
    return PaymentResponse.model_validate(payment)


@router.get("")
def list_payments(
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """List payments for tenant (multi-tenant enforced)."""
    tenant_id = uuid.UUID(tenant_id_str)

    service = PaymentService(db)
    payments = service.list_tenant_payments(tenant_id)
    return [PaymentResponse.model_validate(p) for p in payments]
