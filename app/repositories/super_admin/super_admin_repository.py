import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.super_admin import SuperAdmin


class SuperAdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> SuperAdmin | None:
        normalized_email = email.strip().lower()
        stmt = select(SuperAdmin).where(func.lower(SuperAdmin.email) == normalized_email)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, *, name: str, email: str, password_hash: str) -> SuperAdmin:
        entity = SuperAdmin(name=name, email=email, password_hash=password_hash)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list_all(self) -> list[SuperAdmin]:
        stmt = select(SuperAdmin).order_by(SuperAdmin.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, super_admin_id: uuid.UUID) -> SuperAdmin | None:
        stmt = select(SuperAdmin).where(SuperAdmin.id == super_admin_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_password(self, super_admin: SuperAdmin, password_hash: str) -> SuperAdmin:
        super_admin.password_hash = password_hash
        self.db.commit()
        self.db.refresh(super_admin)
        return super_admin
