import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.auth import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = Field(default=UserRole.STAFF)


class UserStaffCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    # Response uses str to avoid runtime 500 with legacy invalid emails in DB.
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
