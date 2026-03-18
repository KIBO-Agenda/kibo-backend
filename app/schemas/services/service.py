import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    duration: int = Field(ge=5, le=480)
    price: Decimal = Field(ge=0, decimal_places=2)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    duration: int | None = Field(default=None, ge=5, le=480)
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class ServiceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    duration: int
    price: Decimal
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
