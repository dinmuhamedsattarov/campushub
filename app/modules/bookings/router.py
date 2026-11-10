import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.modules.auth.dependencies import get_current_user
from app.modules.bookings.schemas import BookingCreateRequest, BookingResponse
from app.modules.bookings.service import BookingService

router = APIRouter(prefix="/bookings", tags=["3. Booking System"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    payload: BookingCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    return await BookingService(db).reserve_ticket(
        payload=payload,
        user=current_user,
        idempotency_key=idempotency_key,
    )


@router.get("/my", response_model=list[BookingResponse])
async def list_my_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BookingResponse]:
    return await BookingService(db).list_user_bookings(current_user)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    return await BookingService(db).cancel_booking(booking_id, current_user)
