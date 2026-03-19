import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.waitlists import WaitlistRepository


class WaitlistService:
    def __init__(self, db: Session) -> None:
        self.waitlist_repo = WaitlistRepository(db)

    def create_waitlist(
        self,
        tenant_id: uuid.UUID,
        *,
        client_name: str,
        client_phone: str | None,
        target_date: date,
        notes: str | None,
    ):
        return self.waitlist_repo.create(
            tenant_id=tenant_id,
            client_name=client_name,
            client_phone=client_phone,
            target_date=target_date,
            notes=notes,
        )

    def list_waitlists(self, tenant_id: uuid.UUID, *, target_date: date):
        return self.waitlist_repo.list_unresolved_by_date(tenant_id, target_date)

    def resolve_waitlist(self, tenant_id: uuid.UUID, waitlist_id: uuid.UUID):
        entity = self.waitlist_repo.resolve(tenant_id, waitlist_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Waitlist item not found")
        return entity
