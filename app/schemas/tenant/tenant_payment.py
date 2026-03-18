import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    payment_method: str | None = Field(None, max_length=100)
    reference_code: str | None = Field(None, max_length=255)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    amount: Decimal
    payment_date: datetime
    payment_method: str | None
    reference_code: str | None

    model_config = {"from_attributes": True}
