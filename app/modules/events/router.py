import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.event import EventCategory
from app.models.user import User, UserRole
from app.modules.auth.dependencies import require_roles
from app.modules.events.schemas import (
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
    OrganizerDashboardStats,
    PaginatedEventsResponse,
)
from app.modules.events.service import EventService

router = APIRouter(prefix="/events", tags=["2. Event Management"])


@router.get("", response_model=PaginatedEventsResponse)
async def list_events(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(default=10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search title, description, location"),
    category: EventCategory | None = Query(default=None, description="Filter by category"),
    only_available: bool = Query(default=False, description="Only show events with free spots"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedEventsResponse:
    return await EventService(db).list_events(
        page=page,
        size=size,
        search=search,
        category=category,
        only_available=only_available,
    )


@router.get("/categories", response_model=list[str])
async def list_event_categories() -> list[str]:
    return [c.value for c in EventCategory]


@router.get("/organizer/dashboard", response_model=OrganizerDashboardStats)
async def get_organizer_dashboard(
    current_user: User = Depends(require_roles(UserRole.ORGANIZER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> OrganizerDashboardStats:
    return await EventService(db).get_organizer_dashboard(current_user)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_details(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    event = await EventService(db).get_event_or_404(event_id)
    return EventResponse.model_validate(event)


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    payload: EventCreateRequest,
    current_user: User = Depends(require_roles(UserRole.ORGANIZER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    return await EventService(db).create_event(payload, current_user)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: uuid.UUID,
    payload: EventUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ORGANIZER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    return await EventService(db).update_event(event_id, payload, current_user)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.ORGANIZER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await EventService(db).delete_event(event_id, current_user)
