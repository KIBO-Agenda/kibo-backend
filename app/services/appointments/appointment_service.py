import uuid
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.appointments import AppointmentStatus
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
        user_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> tuple[int, object]:
        assigned_user = self.user_repo.get_by_id(tenant_id, user_id)
        if not assigned_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")

        service = self.service_repo.get_by_id(tenant_id, service_id)
        if not service or not service.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found or inactive")

        return service.duration, assigned_user

    def _resolve_client_id(
        self,
        tenant_id: uuid.UUID,
        *,
        client_id: uuid.UUID | None,
        client_name: str | None,
        client_phone: str | None,
    ) -> uuid.UUID:
        normalized_name = client_name.strip() if client_name else None
        normalized_phone = client_phone.strip() if client_phone else None

        if client_id is not None:
            client = self.client_repo.get_by_id(tenant_id, client_id)
            if not client:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
            return client.id

        if normalized_phone:
            existing_client = self.client_repo.get_by_phone(tenant_id, normalized_phone)
            if existing_client:
                return existing_client.id
            created_client = self.client_repo.create(
                tenant_id=tenant_id,
                name=normalized_name or "Client",
                phone=normalized_phone,
            )
            return created_client.id

        if normalized_name:
            existing_client = self.client_repo.get_by_name_without_phone(tenant_id, normalized_name)
            if existing_client:
                return existing_client.id
            created_client = self.client_repo.create(
                tenant_id=tenant_id,
                name=normalized_name,
                phone=None,
            )
            return created_client.id

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either client_id or client_name is required",
        )

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
        client_id: uuid.UUID | None,
        client_name: str | None,
        client_phone: str | None,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        appointment_date: date,
        time_start: time,
        notes: str | None = None,
    ):
        resolved_client_id = self._resolve_client_id(
            tenant_id,
            client_id=client_id,
            client_name=client_name,
            client_phone=client_phone,
        )

        duration, _ = self._validate_references(
            tenant_id,
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
            client_id=resolved_client_id,
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

    def get_agenda(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        *,
        start_date: date,
        end_date: date | None = None,
    ) -> dict:
        if end_date is None:
            end_date = start_date

        if end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date cannot be earlier than start_date",
            )

        # Staff sees only own appointments; owner sees whole tenant.
        filtered_user_id = current_user.id if current_user.role == UserRole.STAFF else None

        summary = self.appointment_repo.get_agenda_summary(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            user_id=filtered_user_id,
        )
        rows = self.appointment_repo.list_agenda_appointments(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            user_id=filtered_user_id,
        )

        appointments = [
            {
                "id": row.id,
                "time_start": row.time_start.strftime("%H:%M"),
                "time_end": row.time_end.strftime("%H:%M"),
                "client_name": row.client_name,
                "status": row.status,
                "staff_name": row.staff_name,
                "service_name": row.service_name,
            }
            for row in rows
        ]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
            "appointments": appointments,
        }

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

    def change_status(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        appointment_id: uuid.UUID,
        *,
        new_status: AppointmentStatus,
    ):
        entity = self.appointment_repo.get_by_id(tenant_id, appointment_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        if current_user.role == UserRole.STAFF and entity.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff can only modify their own appointments",
            )

        if entity.status in (AppointmentStatus.CANCELLED, AppointmentStatus.ATTENDED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change status of {entity.status.value} appointment",
            )

        return self.appointment_repo.update(
            tenant_id,
            appointment_id,
            status=new_status,
        )

    def reschedule_appointment(
        self,
        tenant_id: uuid.UUID,
        current_user: User,
        appointment_id: uuid.UUID,
        *,
        new_date: date,
        new_time_start: time,
    ):
        entity = self.appointment_repo.get_by_id(tenant_id, appointment_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        if current_user.role == UserRole.STAFF and entity.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff can only reschedule their own appointments",
            )

        duration, _ = self._validate_references(
            tenant_id,
            user_id=entity.user_id,
            service_id=entity.service_id,
        )

        new_time_end = self._calculate_end_time(new_time_start, duration)
        if new_time_end <= new_time_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment duration exceeds day boundary",
            )

        if self.appointment_repo.has_overlap(
            tenant_id=tenant_id,
            user_id=entity.user_id,
            appointment_date=new_date,
            time_start=new_time_start,
            time_end=new_time_end,
            exclude_appointment_id=appointment_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="New time slot overlaps with existing schedule",
            )

        return self.appointment_repo.update(
            tenant_id,
            appointment_id,
            appointment_date=new_date,
            time_start=new_time_start,
            time_end=new_time_end,
        )
