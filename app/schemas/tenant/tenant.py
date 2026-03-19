import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.tenant import SubscriptionStatus


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    slot_duration: int = Field(default=15, ge=5, le=120)
    max_users: int = Field(default=5, ge=1, le=500)


class BusinessHourDay(BaseModel):
    is_open: bool
    open: str
    close: str

    @field_validator("open", "close")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Time must have HH:MM format")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise ValueError("Time must have HH:MM format") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Time must have HH:MM format")
        return value

    @model_validator(mode="after")
    def validate_range(self):
        if self.is_open and self.open >= self.close:
            raise ValueError("open must be earlier than close when is_open is true")
        return self


BusinessHours = dict[str, BusinessHourDay]


def default_business_hours_payload() -> BusinessHours:
    return {
        "monday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "tuesday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "wednesday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "thursday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "friday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "saturday": BusinessHourDay(is_open=True, open="08:00", close="18:00"),
        "sunday": BusinessHourDay(is_open=False, open="08:00", close="18:00"),
    }


class TenantBusinessHoursMixin(BaseModel):
    business_hours: BusinessHours = Field(default_factory=default_business_hours_payload)

    @field_validator("business_hours")
    @classmethod
    def validate_business_hours_keys(cls, value: BusinessHours) -> BusinessHours:
        required = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        received = set(value.keys())
        if received != required:
            raise ValueError("business_hours must include monday-sunday keys")
        return value


class TenantCreateWithHours(TenantCreate, TenantBusinessHoursMixin):
    pass


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    slot_duration: int | None = Field(None, ge=5, le=120)
    max_users: int | None = Field(None, ge=1, le=500)
    business_hours: BusinessHours | None = None


class TenantSettingsUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    slot_duration: int | None = Field(None, ge=5, le=120)
    business_hours: BusinessHours | None = None

    @field_validator("business_hours")
    @classmethod
    def validate_settings_business_hours(cls, value: BusinessHours | None) -> BusinessHours | None:
        if value is None:
            return value
        required = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        if set(value.keys()) != required:
            raise ValueError("business_hours must include monday-sunday keys")
        return value


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    subscription_status: SubscriptionStatus
    subscription_valid_until: datetime
    slot_duration: int
    max_users: int
    business_hours: BusinessHours
    created_at: datetime

    model_config = {"from_attributes": True}
