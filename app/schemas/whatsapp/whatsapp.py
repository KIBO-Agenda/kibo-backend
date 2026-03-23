from pydantic import BaseModel, Field


class OutboxEnqueueRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)
    message_type: str = Field(min_length=3, max_length=50)
    variables: dict[str, str] = Field(default_factory=dict)


class OutboxStatsResponse(BaseModel):
    pending: int
    processing: int
    sent: int
    failed: int
    blocked_opt_out: int


class WebhookProcessResponse(BaseModel):
    accepted: bool = True
    matched_keyword: bool = False
    opt_out_applied: bool = False
    reason: str | None = None


class WhatsAppInstanceResponse(BaseModel):
    instance_name: str
    status: str


class WhatsAppQrResponse(BaseModel):
    instance_name: str
    qr_base64: str


class WhatsAppStatusResponse(BaseModel):
    instance_name: str | None
    status: str
    connected: bool
    phone: str | None = None


class WhatsAppLogoutResponse(BaseModel):
    ok: bool
    instance_name: str | None
    status: str
