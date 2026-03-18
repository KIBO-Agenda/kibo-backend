from datetime import date
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_tenant_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.appointments import (
    AppointmentAgendaResponse,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentStatusUpdate,
    AppointmentUpdate,
    AppointmentWeeklyResponse,
)
from app.services.appointments import AppointmentService

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    entity = service.create_appointment(
        current_user.tenant_id,
        current_user,
        client_id=payload.client_id,
        client_name=payload.client_name,
        client_phone=payload.client_phone,
        user_id=payload.user_id,
        service_id=payload.service_id,
        appointment_date=payload.appointment_date,
        time_start=payload.time_start,
        notes=payload.notes,
    )
    return AppointmentResponse.model_validate(entity)


@router.get("/agenda", response_model=AppointmentAgendaResponse)
def get_agenda(
    start_date: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    end_date: Annotated[date | None, Query()] = None,
):
    service = AppointmentService(db)
    data = service.get_agenda(
        current_user.tenant_id,
        current_user,
        start_date=start_date,
        end_date=end_date,
    )
    return AppointmentAgendaResponse.model_validate(data)


@router.get("/weekly", response_model=AppointmentWeeklyResponse)
def get_weekly_agenda(
    start_date: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    staff_id: Annotated[uuid.UUID | None, Query()] = None,
):
    service = AppointmentService(db)
    data = service.get_weekly_agenda(
        current_user.tenant_id,
        current_user,
        start_date=start_date,
        staff_id=staff_id,
    )
    return AppointmentWeeklyResponse.model_validate(data)


@router.get("")
def list_appointments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    appointment_date: Annotated[date | None, Query()] = None,
):
    service = AppointmentService(db)
    entities = service.list_appointments(
        current_user.tenant_id,
        current_user,
        appointment_date=appointment_date,
    )
    return [AppointmentResponse.model_validate(entity) for entity in entities]


@router.patch("/{appointment_id}/status")
def change_appointment_status(
    appointment_id: uuid.UUID,
    payload: AppointmentStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    entity = service.change_status(
        current_user.tenant_id,
        current_user,
        appointment_id,
        new_status=payload.status,
    )
    return AppointmentResponse.model_validate(entity)


@router.patch("/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentReschedule,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    entity = service.reschedule_appointment(
        current_user.tenant_id,
        current_user,
        appointment_id,
        new_date=payload.appointment_date,
        new_time_start=payload.time_start,
    )
    return AppointmentResponse.model_validate(entity)


@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    entity = service.get_appointment(current_user.tenant_id, current_user, appointment_id)
    return AppointmentResponse.model_validate(entity)


@router.patch("/{appointment_id}")
def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    entity = service.update_appointment(
        current_user.tenant_id,
        current_user,
        appointment_id,
        client_id=payload.client_id,
        user_id=payload.user_id,
        service_id=payload.service_id,
        appointment_date=payload.appointment_date,
        time_start=payload.time_start,
        appointment_status=payload.status,
        notes=payload.notes,
    )
    return AppointmentResponse.model_validate(entity)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_appointment(
    appointment_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = AppointmentService(db)
    service.cancel_appointment(current_user.tenant_id, current_user, appointment_id)
