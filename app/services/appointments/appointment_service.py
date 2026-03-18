import uuid
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.auth import User, UserRole
from app.repositories.appointments import AppointmentRepository
from app.repositories.clients import ClientRepository
from app.repositories.services import ServiceRepository
from app.repositories.users import UserRepository


class AppointmentService:
    def __init__(self, db: Session) -> None:
        self.appointment_repo = AppointmentRepository(db)
        self.client_repo = ClientRepository(db)
        self.service_repo = ServiceRepository(db)
        self.user_repo = UserRepository(db)

    def _validate_references(
        self,
        tenant_id: uuid.UUID,
        *,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> tuple[int, object]:
        client = self.client_repo.get_by_id(tenant_id, client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

        assigned_user = self.user_repo.get_by_id(tenant_id, user_id)
        if not assigned_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")

        service = self.service_repo.get_by_id(tenant_id, service_id)
        if not service or not service.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found or inactive")

        return service.duration, assigned_user

    @staticmethod
    def _calculate_end_time(time_start: time, duration_minutes: int) -> time:
        start_dt = datetime.combine(date.today(), time_start)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        return end_dt.time()

    def create_appointment(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        *,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        appointment_date: date,
        time_start: time,
        notes: str | None = None,
    ):
        duration, _ = self._validate_references(
            tenant_id,
            client_id=client_id,
            user_id=user_id,
            service_id=service_id,
        )

        # staff can only manage own appointments
        if current_user.role == UserRole.STAFF and current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff can only manage their own appointments",
            )

        time_end = self._calculate_end_time(time_start, duration)
        if time_end <= time_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment duration exceeds day boundary",
            )

        if self.appointment_repo.has_overlap(
            tenant_id=tenant_id,
            user_id=user_id,
            appointment_date=appointment_date,
            time_start=time_start,
            time_end=time_end,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Appointment overlaps with existing schedule",
            )

        return self.appointment_repo.create(
            tenant_id=tenant_id,
            client_id=client_id,
            user_id=user_id,
            service_id=service_id,
            appointment_date=appointment_date,
            time_start=time_start,
            time_end=time_end,
            notes=notes,
        )

    def get_appointment(self, tenant_id: uuid.UUID, current_user: User, appointment_id: uuid.UUID):
        entity = self.appointment_repo.get_by_id(tenant_id, appointment_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        if current_user.role == UserRole.STAFF and entity.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff can only access their own appointments",
            )
        return entity

    def list_appointments(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        *,
        appointment_date: date | None = None,
    ):
        if current_user.role == UserRole.STAFF:
            return self.appointment_repo.list_by_user(
                tenant_id,
                current_user.id,
                appointment_date=appointment_date,
            )
        return self.appointment_repo.list_by_tenant(tenant_id, appointment_date=appointment_date)

    def update_appointment(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        appointment_id: uuid.UUID,
        *,
        client_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        appointment_date: date | None = None,
        time_start: time | None = None,
        appointment_status=None,
        notes: str | None = None,
    ):
        entity = self.appointment_repo.get_by_id(tenant_id, appointment_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        # staff can only manage own appointments and cannot reassign user
        if current_user.role == UserRole.STAFF:
            if entity.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff can only manage their own appointments",
                )
            if user_id is not None and user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff cannot reassign appointments",
                )

        next_client_id = client_id or entity.client_id
        next_user_id = user_id or entity.user_id
        next_service_id = service_id or entity.service_id
        next_date = appointment_date or entity.appointment_date
        next_start = time_start or entity.time_start

        duration, _ = self._validate_references(
            tenant_id,
            client_id=next_client_id,
            user_id=next_user_id,
            service_id=next_service_id,
        )
        next_end = self._calculate_end_time(next_start, duration)

        if next_end <= next_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment duration exceeds day boundary",
            )

        if self.appointment_repo.has_overlap(
            tenant_id=tenant_id,
            user_id=next_user_id,
            appointment_date=next_date,
            time_start=next_start,
            time_end=next_end,
            exclude_appointment_id=appointment_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Appointment overlaps with existing schedule",
            )

        return self.appointment_repo.update(
            tenant_id,
            appointment_id,
            client_id=next_client_id,
            user_id=next_user_id,
            service_id=next_service_id,
            appointment_date=next_date,
            time_start=next_start,
            time_end=next_end,
            status=appointment_status,
            notes=notes,
        )

    def cancel_appointment(self, tenant_id: uuid.UUID, current_user: User, appointment_id: uuid.UUID):
        entity = self.appointment_repo.get_by_id(tenant_id, appointment_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        if current_user.role == UserRole.STAFF and entity.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff can only cancel their own appointments",
            )

        self.appointment_repo.cancel(tenant_id, appointment_id)
