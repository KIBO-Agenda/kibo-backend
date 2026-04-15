from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_tenant_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentSessionResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SuperAdminLoginRequest,
    TokenPairResponse,
    UserLoginRequest,
)
from app.services.auth.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentSessionResponse)
def get_me(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AuthService(db)
    data = service.get_current_session(current_user)
    return CurrentSessionResponse.model_validate(data)


@router.post("/login")
def login_user(
    payload: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    _, access_token, refresh_token, plan_tier = service.login_user(
        email=payload.email,
        password=payload.password,
    )
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        plan_tier=plan_tier,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_public_owner(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    data = service.register_public_owner(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        business_name=payload.business_name,
    )
    return RegisterResponse.model_validate(data)


@router.post("/super-admin/login")
def login_super_admin(
    payload: SuperAdminLoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    _, access_token, refresh_token = service.login_super_admin(
        email=payload.email,
        password=payload.password,
    )
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    service.forgot_password(email=payload.email)
    return MessageResponse(message="If the email exists, a recovery link has been sent")


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    service.reset_password(token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="Password updated successfully")


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
):
    service = AuthService(db)
    service.change_password(
        authorization=authorization or "",
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password changed successfully")
