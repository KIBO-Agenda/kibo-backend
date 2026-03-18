import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.appointments import AppointmentStatus


class AppointmentCreate(BaseModel):
    client_id: uuid.UUID
    user_id: uuid.UUID
    service_id: uuid.UUID
    appointment_date: date
    time_start: time
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    client_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    appointment_date: date | None = None
    time_start: time | None = None
    status: AppointmentStatus | None = None
    notes: str | None = None


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    client_id: uuid.UUID
    user_id: uuid.UUID
    service_id: uuid.UUID
    appointment_date: date
    time_start: time
    time_end: time
    status: AppointmentStatus
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
