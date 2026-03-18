import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.auth.user import UserRole


class UserLoginRequest(BaseModel):
    tenant_id: uuid.UUID
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserAuthResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SuperAdminLoginRequest(BaseModel):
    email: EmailStr
    password: str
