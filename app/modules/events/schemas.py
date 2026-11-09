from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.event import EventCategory


class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=10, max_length=5000)
    category: EventCategory = EventCategory.OTHER
    location: str = Field(..., min_length=2, max_length=255)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(..., gt=0, le=50000)
    is_published: bool = True

    @model_validator(mode="after")
    def validate_dates(self) -> "EventCreateRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time.")
        return self


class EventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    category: EventCategory | None = None
    location: str | None = Field(default=None, min_length=2, max_length=255)
    start_time: datetime | None = None
    end_time: datetime | None = None
    capacity: int | None = Field(default=None, gt=0, le=50000)
    is_published: bool | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    category: EventCategory
    location: str
    start_time: datetime
    end_time: datetime
    capacity: int
    booked_count: int
    available_spots: int
    is_published: bool
    organizer_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PaginatedEventsResponse(BaseModel):
    items: list[EventResponse]
    total: int
    page: int
    size: int
    pages: int


class OrganizerDashboardStats(BaseModel):
    total_events: int
    published_events: int
    total_capacity: int
    total_booked: int
    overall_occupancy_rate: float
    events: list[EventResponse]
