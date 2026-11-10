from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class BookingCreateRequest(BaseModel):
    event_id: uuid.UUID
    join_waitlist_if_full: bool = False


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    status: BookingStatus
    ticket_code: str
    qr_code_base64: str | None
    waitlist_position: int | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
