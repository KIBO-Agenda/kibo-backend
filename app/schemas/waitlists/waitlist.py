import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class WaitlistCreate(BaseModel):
    service_id: uuid.UUID | None = None
    client_name: str = Field(min_length=1, max_length=255)
    client_phone: str | None = Field(default=None, min_length=4, max_length=30)
    target_date: date
    notes: str | None = None


class WaitlistResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID | None
    client_name: str
    client_phone: str | None
    target_date: date
    notes: str | None
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
