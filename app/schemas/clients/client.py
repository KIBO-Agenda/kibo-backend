import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=4, max_length=30)
    notes: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=4, max_length=30)
    notes: str | None = None


class ClientResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    phone: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
