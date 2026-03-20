import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.auth.user import UserRole


class UserLoginRequest(BaseModel):
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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class CurrentSessionTenant(BaseModel):
    name: str
    slot_duration: int


class CurrentSessionResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: UserRole
    tenant_id: uuid.UUID
    tenant: CurrentSessionTenant


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    business_name: str = Field(min_length=1, max_length=255)


class RegisterResponse(BaseModel):
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    business_name: str
    trial_ends_at: datetime
