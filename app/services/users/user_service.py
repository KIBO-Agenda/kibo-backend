import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.auth import UserRole
from app.repositories.tenant import TenantRepository
from app.repositories.users import UserRepository


class UserService:
    """Single Responsibility: manage tenant users with multi-tenant enforcement."""

    def __init__(self, db: Session) -> None:
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.logger = logging.getLogger(__name__)

    def _enforce_active_staff_limit(self, tenant_id: uuid.UUID) -> None:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        # Plan quota counts active staff only. Owner is intentionally excluded.
        active_staff = self.user_repo.count_staff_by_tenant(tenant_id, only_active=True)
        if active_staff >= tenant.max_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Limite de especialistas alcanzado",
            )

    def create_user(
        self,
        tenant_id: uuid.UUID,
        *,
        email: str,
        name: str,
        password: str,
        role: UserRole = UserRole.STAFF,
    ):
        """Create user within tenant."""
        # Validate tenant exists
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        # Check email uniqueness across platform (not tenant-scoped)
        normalized_email = email.strip().lower()
        existing_by_email = self.user_repo.get_by_email(tenant_id, normalized_email)
        if existing_by_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )

        # Hash and create
        password_hash = get_password_hash(password)
        return self.user_repo.create(
            tenant_id=tenant_id,
            email=normalized_email,
            name=name,
            password_hash=password_hash,
            role=role.value,
        )

    def get_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID):
        """Get user with multi-tenant enforcement."""
        user = self.user_repo.get_by_id(tenant_id, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    def list_users(self, tenant_id: uuid.UUID):
        """List all users in tenant."""
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return self.user_repo.list_by_tenant(tenant_id)

    def update_user(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ):
        """Update user fields with multi-tenant enforcement."""
        user = self.user_repo.update(
            tenant_id,
            user_id,
            name=name,
            role=role.value if role else None,
            is_active=is_active,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    def delete_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID):
        """Soft-delete user with multi-tenant enforcement."""
        success = self.user_repo.delete(tenant_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        self.logger.info(
            "Audit: staff deactivated",
            extra={"tenant_id": str(tenant_id), "user_id": str(user_id), "action": "deactivate_staff"},
        )

    def create_staff_user(
        self,
        tenant_id: uuid.UUID,
        *,
        email: str,
        name: str,
        password: str,
    ):
        self._enforce_active_staff_limit(tenant_id)

        normalized_email = email.strip().lower()
        existing_by_email = self.user_repo.get_by_email(tenant_id, normalized_email)
        if existing_by_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )

        password_hash = get_password_hash(password)
        return self.user_repo.create(
            tenant_id=tenant_id,
            email=normalized_email,
            name=name,
            password_hash=password_hash,
            role=UserRole.STAFF.value,
        )

    def activate_staff_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID):
        user = self.user_repo.get_by_id(tenant_id, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if user.role != UserRole.STAFF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only staff users can be activated",
            )

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already active",
            )

        self._enforce_active_staff_limit(tenant_id)

        activated = self.user_repo.update(tenant_id, user_id, is_active=True)
        if not activated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        self.logger.info(
            "Audit: staff activated",
            extra={"tenant_id": str(tenant_id), "user_id": str(user_id), "action": "activate_staff"},
        )
        return activated
