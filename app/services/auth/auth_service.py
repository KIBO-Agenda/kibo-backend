import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import send_password_reset_email
from app.core.security import (
    create_password_reset_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.auth import User
from app.models.super_admin import SuperAdmin
from app.repositories.auth import AuthRepository
from app.repositories.super_admin import SuperAdminRepository
from app.repositories.tenant import TenantRepository


class AuthService:
    def __init__(self, db: Session) -> None:
        self.auth_repository = AuthRepository(db)
        self.super_admin_repository = SuperAdminRepository(db)
        self.tenant_repository = TenantRepository(db)
        self.settings = get_settings()

    def get_current_session(self, current_user: User) -> dict:
        tenant = self.tenant_repository.get_by_id(current_user.tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        return {
            "id": current_user.id,
            "name": current_user.name,
            "role": current_user.role,
            "tenant_id": current_user.tenant_id,
            "tenant": {
                "name": tenant.name,
                "slot_duration": tenant.slot_duration,
            },
        }

    def login_user(self, *, email: str, password: str) -> tuple[User, str, str]:
        user = self.auth_repository.get_user_by_email(email=email)
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

    def forgot_password(self, *, email: str) -> None:
        """Generate reset token and send recovery email.

        Security note: this method does not reveal whether the email exists.
        """
        normalized_email = email.strip().lower()

        user = self.auth_repository.get_user_by_email(normalized_email)
        if user:
            token = create_password_reset_token(
                {
                    "sub": str(user.id),
                    "scope": "tenant_user",
                    "tenant_id": str(user.tenant_id),
                }
            )
            reset_link = f"{self.settings.FRONTEND_URL}/reset-password?token={token}"
            send_password_reset_email(normalized_email, reset_link)
            return

        super_admin = self.super_admin_repository.get_by_email(normalized_email)
        if super_admin:
            token = create_password_reset_token(
                {
                    "sub": str(super_admin.id),
                    "scope": "super_admin",
                }
            )
            reset_link = f"{self.settings.FRONTEND_URL}/reset-password?token={token}"
            send_password_reset_email(normalized_email, reset_link)

    def reset_password(self, *, token: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password must be at least 8 characters",
            )

        try:
            payload = decode_token(token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token",
            ) from exc

        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token type",
            )

        sub = payload.get("sub")
        scope = payload.get("scope")
        if not sub or not scope:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token payload",
            )

        try:
            subject_id = uuid.UUID(sub)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token subject",
            ) from exc

        password_hash = get_password_hash(new_password)
        if scope == "tenant_user":
            user = self.auth_repository.get_user_by_id(subject_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )
            self.auth_repository.update_password(user, password_hash)
            return

        if scope == "super_admin":
            super_admin = self.super_admin_repository.get_by_id(subject_id)
            if not super_admin:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Super admin not found",
                )
            self.super_admin_repository.update_password(super_admin, password_hash)
            return

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported reset scope",
        )

    def change_password(self, *, authorization: str, current_password: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password must be at least 8 characters",
            )

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header",
            )

        token = authorization.split(" ")[1]
        try:
            payload = decode_token(token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from exc

        sub = payload.get("sub")
        scope = payload.get("scope")
        if not sub or not scope:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        try:
            subject_id = uuid.UUID(sub)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            ) from exc

        password_hash = get_password_hash(new_password)
        if scope == "tenant_user":
            user = self.auth_repository.get_user_by_id(subject_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            if not verify_password(current_password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
            self.auth_repository.update_password(user, password_hash)
            return

        if scope == "super_admin":
            super_admin = self.super_admin_repository.get_by_id(subject_id)
            if not super_admin:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Super admin not found")
            if not verify_password(current_password, super_admin.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
            self.super_admin_repository.update_password(super_admin, password_hash)
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported token scope",
        )
