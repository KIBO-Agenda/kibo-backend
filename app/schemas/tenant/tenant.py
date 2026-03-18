import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.tenant import SubscriptionStatus


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    slot_duration: int = Field(default=15, ge=5, le=120)


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    slot_duration: int | None = Field(None, ge=5, le=120)


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    subscription_status: SubscriptionStatus
    subscription_valid_until: datetime
    slot_duration: int
    created_at: datetime

    model_config = {"from_attributes": True}
