import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import User


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        stmt = select(User).where(func.lower(User.email) == normalized_email)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_password(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        self.db.commit()
        self.db.refresh(user)
        return user
