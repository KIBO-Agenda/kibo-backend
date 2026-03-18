from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.repositories.super_admin import SuperAdminRepository
from app.schemas.super_admin import SuperAdminCreate


class SuperAdminService:
    def __init__(self, db: Session) -> None:
        self.repository = SuperAdminRepository(db)

    def create_super_admin(self, payload: SuperAdminCreate):
        normalized_email = payload.email.strip().lower()
        existing = self.repository.get_by_email(email=normalized_email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Super admin email already exists",
            )
        return self.repository.create(
            name=payload.name,
            email=normalized_email,
            password_hash=get_password_hash(payload.password),
        )

    def list_super_admins(self):
        return self.repository.list_all()
