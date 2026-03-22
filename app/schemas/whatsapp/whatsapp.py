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
