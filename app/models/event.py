from datetime import datetime, timezone
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EventCategory(str, enum.Enum):
    WORKSHOP = "WORKSHOP"
    SEMINAR = "SEMINAR"
    HACKATHON = "HACKATHON"
    CULTURAL = "CULTURAL"
    SPORTS = "SPORTS"
    CAREER = "CAREER"
    OTHER = "OTHER"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_events_capacity_positive"),
        CheckConstraint("booked_count >= 0", name="ck_events_booked_non_negative"),
        CheckConstraint("booked_count <= capacity", name="ck_events_no_overbooking"),
        Index("ix_events_category_start_time", "category", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, name="event_category_enum"),
        default=EventCategory.OTHER,
        nullable=False,
        index=True,
    )
    location: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    booked_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    organizer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    organizer = relationship("User", lazy="selectin")

    @property
    def available_spots(self) -> int:
        return max(0, self.capacity - self.booked_count)
