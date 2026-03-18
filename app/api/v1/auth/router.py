from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import (
    SuperAdminLoginRequest,
    TokenPairResponse,
    UserLoginRequest,
)
from app.services.auth.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login_user(
    payload: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    service = AuthService(db)
    _, access_token, refresh_token = service.login_user(
        tenant_id=payload.tenant_id,
        email=payload.email,
        password=payload.password,
    )
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


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
