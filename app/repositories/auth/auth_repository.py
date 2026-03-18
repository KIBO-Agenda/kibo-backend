import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id, User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()
