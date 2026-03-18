from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.auth import User
from app.models.super_admin import SuperAdmin
from app.repositories.auth import AuthRepository
from app.repositories.super_admin import SuperAdminRepository


class AuthService:
    def __init__(self, db: Session) -> None:
        self.auth_repository = AuthRepository(db)
        self.super_admin_repository = SuperAdminRepository(db)

    def login_user(self, *, tenant_id, email: str, password: str) -> tuple[User, str, str]:
        user = self.auth_repository.get_user_by_email(tenant_id=tenant_id, email=email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )

        payload = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role.value,
            "scope": "tenant_user",
        }
        return user, create_access_token(payload), create_refresh_token(payload)

    def login_super_admin(self, *, email: str, password: str) -> tuple[SuperAdmin, str, str]:
        normalized_email = email.strip().lower()
        super_admin = self.super_admin_repository.get_by_email(email=normalized_email)
        if not super_admin or not verify_password(password, super_admin.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        payload = {
            "sub": str(super_admin.id),
            "role": "super_admin",
            "scope": "super_admin",
        }
        return (
            super_admin,
            create_access_token(payload),
            create_refresh_token(payload),
        )
