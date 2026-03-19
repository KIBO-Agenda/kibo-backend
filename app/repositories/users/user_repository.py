import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.auth import UserRole


class UserRepository:
    """Single Responsibility: user data access with mandatory multi-tenant filter."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: uuid.UUID,
        email: str,
        name: str,
        password_hash: str,
        role: str = "staff",
    ) -> User:
        """Create user within a tenant."""
        user = User(
            tenant_id=tenant_id,
            email=email,
            name=name,
            password_hash=password_hash,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        """Get user by ID with mandatory multi-tenant filter."""
        stmt = select(User).where(
            and_(User.tenant_id == tenant_id, User.id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        """Get user by email with multi-tenant filter."""
        normalized_email = email.strip().lower()
        stmt = select(User).where(
            and_(
                User.tenant_id == tenant_id,
                func.lower(User.email) == normalized_email,
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID) -> list[User]:
        """List all users in a tenant."""
        stmt = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_by_tenant(self, tenant_id: uuid.UUID, *, only_active: bool = True) -> int:
        stmt = select(func.count(User.id)).where(User.tenant_id == tenant_id)
        if only_active:
            stmt = stmt.where(User.is_active.is_(True))
        return int(self.db.execute(stmt).scalar_one() or 0)

    def count_staff_by_tenant(self, tenant_id: uuid.UUID, *, only_active: bool = True) -> int:
        stmt = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.role == UserRole.STAFF,
        )
        if only_active:
            stmt = stmt.where(User.is_active.is_(True))
        return int(self.db.execute(stmt).scalar_one() or 0)

    def update(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        """Update user fields with multi-tenant filter."""
        user = self.get_by_id(tenant_id, user_id)
        if not user:
            return None

        if name is not None:
            user.name = name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active

        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Soft-delete user by setting is_active=False with multi-tenant filter."""
        user = self.get_by_id(tenant_id, user_id)
        if not user:
            return False

        user.is_active = False
        self.db.commit()
        return True
