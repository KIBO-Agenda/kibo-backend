import uuid
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.waitlists import Waitlist


class WaitlistRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: uuid.UUID,
        service_id: uuid.UUID | None,
        client_name: str,
        client_phone: str | None,
        target_date: date,
        notes: str | None,
    ) -> Waitlist:
        entity = Waitlist(
            tenant_id=tenant_id,
            service_id=service_id,
            client_name=client_name,
            client_phone=client_phone,
            target_date=target_date,
            notes=notes,
            is_resolved=False,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list_unresolved_by_date(self, tenant_id: uuid.UUID, target_date: date) -> list[Waitlist]:
        stmt = (
            select(Waitlist)
            .where(
                Waitlist.tenant_id == tenant_id,
                Waitlist.target_date == target_date,
                Waitlist.is_resolved.is_(False),
            )
            .order_by(Waitlist.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, tenant_id: uuid.UUID, waitlist_id: uuid.UUID) -> Waitlist | None:
        stmt = select(Waitlist).where(
            and_(
                Waitlist.tenant_id == tenant_id,
                Waitlist.id == waitlist_id,
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def resolve(self, tenant_id: uuid.UUID, waitlist_id: uuid.UUID) -> Waitlist | None:
        entity = self.get_by_id(tenant_id, waitlist_id)
        if not entity:
            return None
        if not entity.is_resolved:
            entity.is_resolved = True
            self.db.commit()
            self.db.refresh(entity)
        return entity

    def count_unresolved_between_dates(
        self,
        *,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> int:
        stmt = select(func.count(Waitlist.id)).where(
            Waitlist.tenant_id == tenant_id,
            Waitlist.is_resolved.is_(False),
            Waitlist.target_date >= start_date,
            Waitlist.target_date <= end_date,
        )
        return int(self.db.execute(stmt).scalar_one() or 0)

    def unresolved_counts_by_date(
        self,
        *,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict[date, int]:
        stmt = (
            select(Waitlist.target_date, func.count(Waitlist.id).label("total"))
            .where(
                Waitlist.tenant_id == tenant_id,
                Waitlist.is_resolved.is_(False),
                Waitlist.target_date >= start_date,
                Waitlist.target_date <= end_date,
            )
            .group_by(Waitlist.target_date)
        )
        rows = self.db.execute(stmt).all()
        return {row.target_date: int(row.total or 0) for row in rows}

    def first_unresolved_by_date(
        self,
        tenant_id: uuid.UUID,
        target_date: date,
        service_id: uuid.UUID | None = None,
    ) -> Waitlist | None:
        stmt = (
            select(Waitlist)
            .where(
                Waitlist.tenant_id == tenant_id,
                Waitlist.target_date == target_date,
                Waitlist.is_resolved.is_(False),
            )
            .order_by(Waitlist.created_at.asc())
            .limit(1)
        )
        if service_id is not None:
            stmt = stmt.where(Waitlist.service_id == service_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_first_unresolved_by_phone(self, tenant_id: uuid.UUID, phone: str) -> Waitlist | None:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not digits:
            return None

        variants = {digits}
        if len(digits) > 10:
            variants.add(digits[-10:])
        if len(digits) == 10 and digits.startswith("3"):
            variants.add(f"57{digits}")

        normalized_column = func.regexp_replace(func.coalesce(Waitlist.client_phone, ""), "[^0-9]", "", "g")
        conditions = [normalized_column == variant for variant in variants]

        stmt = (
            select(Waitlist)
            .where(
                Waitlist.tenant_id == tenant_id,
                Waitlist.is_resolved.is_(False),
                or_(*conditions),
            )
            .order_by(Waitlist.created_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_notes(self, tenant_id: uuid.UUID, waitlist_id: uuid.UUID, notes: str | None) -> Waitlist | None:
        entity = self.get_by_id(tenant_id, waitlist_id)
        if not entity:
            return None
        entity.notes = notes
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def first_pending_offer(self, tenant_id: uuid.UUID) -> Waitlist | None:
        stmt = (
            select(Waitlist)
            .where(
                Waitlist.tenant_id == tenant_id,
                Waitlist.is_resolved.is_(False),
                Waitlist.notes.like("KIBO_PENDING_OFFER%"),
            )
            .order_by(Waitlist.created_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
