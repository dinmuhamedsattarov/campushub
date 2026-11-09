import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventCategory
from app.models.user import User, UserRole
from app.modules.events.schemas import (
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
    OrganizerDashboardStats,
    PaginatedEventsResponse,
)


class EventService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_event(
        self, payload: EventCreateRequest, organizer: User
    ) -> EventResponse:
        event = Event(
            title=payload.title,
            description=payload.description,
            category=payload.category,
            location=payload.location,
            start_time=payload.start_time,
            end_time=payload.end_time,
            capacity=payload.capacity,
            booked_count=0,
            is_published=payload.is_published,
            organizer_id=organizer.id,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return EventResponse.model_validate(event)

    async def get_event_or_404(self, event_id: uuid.UUID) -> Event:
        result = await self.db.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        return event

    async def list_events(
        self,
        *,
        page: int = 1,
        size: int = 10,
        search: str | None = None,
        category: EventCategory | None = None,
        only_available: bool = False,
    ) -> PaginatedEventsResponse:
        query = select(Event).where(Event.is_published.is_(True))

        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Event.title.ilike(pattern),
                    Event.description.ilike(pattern),
                    Event.location.ilike(pattern),
                )
            )

        if category:
            query = query.where(Event.category == category)

        if only_available:
            query = query.where(Event.booked_count < Event.capacity)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * size
        paginated_query = (
            query.order_by(Event.start_time.asc(), Event.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.db.execute(paginated_query)
        events = result.scalars().all()

        pages = math.ceil(total / size) if total > 0 else 1
        return PaginatedEventsResponse(
            items=[EventResponse.model_validate(e) for e in events],
            total=total,
            page=page,
            size=size,
            pages=pages,
        )

    async def update_event(
        self,
        event_id: uuid.UUID,
        payload: EventUpdateRequest,
        current_user: User,
    ) -> EventResponse:
        event = await self.get_event_or_404(event_id)

        if event.organizer_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update events that you organized.",
            )

        update_data = payload.model_dump(exclude_unset=True)

        if "capacity" in update_data and update_data["capacity"] < event.booked_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot reduce capacity below current booked_count "
                    f"({event.booked_count})."
                ),
            )

        new_start = update_data.get("start_time", event.start_time)
        new_end = update_data.get("end_time", event.end_time)
        if new_end <= new_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_time must be strictly after start_time.",
            )

        for field, value in update_data.items():
            setattr(event, field, value)

        await self.db.commit()
        await self.db.refresh(event)
        return EventResponse.model_validate(event)

    async def delete_event(self, event_id: uuid.UUID, current_user: User) -> None:
        event = await self.get_event_or_404(event_id)

        if event.organizer_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete events that you organized.",
            )

        await self.db.delete(event)
        await self.db.commit()

    async def get_organizer_dashboard(
        self, organizer: User
    ) -> OrganizerDashboardStats:
        result = await self.db.execute(
            select(Event)
            .where(Event.organizer_id == organizer.id)
            .order_by(Event.start_time.asc())
        )
        events = list(result.scalars().all())

        total_events = len(events)
        published_events = sum(1 for e in events if e.is_published)
        total_capacity = sum(e.capacity for e in events)
        total_booked = sum(e.booked_count for e in events)
        occupancy_rate = (
            round((total_booked / total_capacity) * 100, 2)
            if total_capacity > 0
            else 0.0
        )

        return OrganizerDashboardStats(
            total_events=total_events,
            published_events=published_events,
            total_capacity=total_capacity,
            total_booked=total_booked,
            overall_occupancy_rate=occupancy_rate,
            events=[EventResponse.model_validate(e) for e in events],
        )
