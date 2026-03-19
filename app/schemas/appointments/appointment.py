import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.appointments import AppointmentStatus


class AppointmentCreate(BaseModel):
    client_id: uuid.UUID | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=255)
    client_phone: str | None = Field(default=None, min_length=4, max_length=30)
    user_id: uuid.UUID
    service_id: uuid.UUID
    appointment_date: date
    time_start: time
    notes: str | None = None

    @model_validator(mode="after")
    def validate_client_input(self):
        if self.client_id is None and not self.client_name:
            raise ValueError("Either client_id or client_name is required")
        return self


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


class AppointmentAgendaSummary(BaseModel):
    total: int = Field(default=0)
    confirmed: int = Field(default=0)
    pending: int = Field(default=0)
    cancelled: int = Field(default=0)
    attended: int = Field(default=0)


class AppointmentAgendaItem(BaseModel):
    id: uuid.UUID
    time_start: str
    time_end: str
    client_name: str
    client_phone: str | None
    status: AppointmentStatus
    staff_name: str
    service_name: str


class AppointmentAgendaResponse(BaseModel):
    start_date: date
    end_date: date
    summary: AppointmentAgendaSummary
    appointments: list[AppointmentAgendaItem]


class AppointmentWeeklySummary(BaseModel):
    total: int = Field(default=0)
    confirmed: int = Field(default=0)
    pending: int = Field(default=0)
    cancelled: int = Field(default=0)


class AppointmentDailySummary(BaseModel):
    total: int = Field(default=0)


class AppointmentWeeklyDay(BaseModel):
    date: date
    day_name: str
    daily_summary: AppointmentDailySummary
    appointments: list[AppointmentAgendaItem]


class AppointmentWeeklyResponse(BaseModel):
    start_date: date
    end_date: date
    weekly_summary: AppointmentWeeklySummary
    days: list[AppointmentWeeklyDay]


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus


class AppointmentReschedule(BaseModel):
    appointment_date: date
    time_start: time
