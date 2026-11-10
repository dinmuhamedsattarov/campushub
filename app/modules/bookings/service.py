import base64
from datetime import datetime, timedelta, timezone
import io
import secrets
import uuid

from fastapi import HTTPException, status
import qrcode
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, IdempotencyRecord
from app.models.event import Event
from app.models.user import User
from app.modules.bookings.schemas import BookingCreateRequest, BookingResponse


def generate_qr_base64(payload_text: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(payload_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def reserve_ticket(
        self,
        payload: BookingCreateRequest,
        user: User,
        idempotency_key: str | None = None,
    ) -> BookingResponse:
        # 1. Idempotency Check: return existing booking if key was already processed
        if idempotency_key:
            existing_idem = await self.db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user.id,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            record = existing_idem.scalar_one_or_none()
            if record:
                existing_booking = await self.get_booking_or_404(record.booking_id)
                return BookingResponse.model_validate(existing_booking)

        # 2. Prevent duplicate active booking by the same user for the same event
        active_check = await self.db.execute(
            select(Booking).where(
                Booking.user_id == user.id,
                Booking.event_id == payload.event_id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.WAITLISTED]),
            )
        )
        if active_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active booking or waitlist spot for this event.",
            )

        # 3. Row-level lock (SELECT ... FOR UPDATE) + Atomic capacity increment
        event_query = (
            select(Event)
            .where(Event.id == payload.event_id, Event.is_published.is_(True))
            .with_for_update()
        )
        event_res = await self.db.execute(event_query)
        event = event_res.scalar_one_or_none()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found or not published.",
            )

        ticket_code = f"CH-{secrets.token_hex(6).upper()}"
        now = datetime.now(timezone.utc)
        booking_id = uuid.uuid4()

        # Atomic conditional update guarantees booked_count never exceeds capacity
        atomic_inc = await self.db.execute(
            update(Event)
            .where(Event.id == payload.event_id, Event.booked_count < Event.capacity)
            .values(booked_count=Event.booked_count + 1)
        )

        if atomic_inc.rowcount == 1:
            qr_data = f"CAMPUSHUB|TICKET:{ticket_code}|EVENT:{event.id}|USER:{user.id}"
            booking = Booking(
                id=booking_id,
                user_id=user.id,
                event_id=event.id,
                status=BookingStatus.CONFIRMED,
                ticket_code=ticket_code,
                qr_code_base64=generate_qr_base64(qr_data),
                expires_at=now + timedelta(hours=24),
                created_at=now,
                updated_at=now,
            )
        else:
            if not payload.join_waitlist_if_full:
                await self.db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Event is at full capacity. No seats remaining.",
                )

            waitlist_count_res = await self.db.execute(
                select(func.count()).where(
                    Booking.event_id == event.id,
                    Booking.status == BookingStatus.WAITLISTED,
                )
            )
            next_pos = waitlist_count_res.scalar_one() + 1
            booking = Booking(
                id=booking_id,
                user_id=user.id,
                event_id=event.id,
                status=BookingStatus.WAITLISTED,
                ticket_code=ticket_code,
                waitlist_position=next_pos,
                created_at=now,
                updated_at=now,
            )

        self.db.add(booking)

        if idempotency_key:
            self.db.add(
                IdempotencyRecord(
                    user_id=user.id,
                    idempotency_key=idempotency_key,
                    booking_id=booking_id,
                )
            )

        try:
            await self.db.commit()
        except (IntegrityError, OperationalError) as exc:
            await self.db.rollback()
            if idempotency_key:
                retry_idem = await self.db.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.user_id == user.id,
                        IdempotencyRecord.idempotency_key == idempotency_key,
                    )
                )
                rec = retry_idem.scalar_one_or_none()
                if rec:
                    b = await self.get_booking_or_404(rec.booking_id)
                    return BookingResponse.model_validate(b)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent booking conflict.",
            ) from exc

        return BookingResponse.model_validate(booking)

    async def get_booking_or_404(self, booking_id: uuid.UUID) -> Booking:
        res = await self.db.execute(select(Booking).where(Booking.id == booking_id))
        booking = res.scalar_one_or_none()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found."
            )
        return booking

    async def list_user_bookings(self, user: User) -> list[BookingResponse]:
        res = await self.db.execute(
            select(Booking)
            .where(Booking.user_id == user.id)
            .order_by(Booking.created_at.desc())
        )
        return [BookingResponse.model_validate(b) for b in res.scalars().all()]

    async def cancel_booking(
        self, booking_id: uuid.UUID, user: User
    ) -> BookingResponse:
        booking = await self.get_booking_or_404(booking_id)
        if booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own bookings.",
            )
        if booking.status in (BookingStatus.CANCELLED, BookingStatus.EXPIRED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking is already {booking.status.value}.",
            )

        was_confirmed = booking.status == BookingStatus.CONFIRMED
        now = datetime.now(timezone.utc)
        booking.status = BookingStatus.CANCELLED
        booking.waitlist_position = None
        booking.updated_at = now

        if was_confirmed:
            next_waitlisted_res = await self.db.execute(
                select(Booking)
                .where(
                    Booking.event_id == booking.event_id,
                    Booking.status == BookingStatus.WAITLISTED,
                )
                .order_by(Booking.waitlist_position.asc(), Booking.created_at.asc())
                .limit(1)
                .with_for_update()
            )
            promoted = next_waitlisted_res.scalar_one_or_none()
            if promoted:
                qr_data = f"CAMPUSHUB|TICKET:{promoted.ticket_code}|EVENT:{promoted.event_id}|USER:{promoted.user_id}"
                promoted.status = BookingStatus.CONFIRMED
                promoted.waitlist_position = None
                promoted.qr_code_base64 = generate_qr_base64(qr_data)
                promoted.updated_at = now
            else:
                await self.db.execute(
                    update(Event)
                    .where(Event.id == booking.event_id, Event.booked_count > 0)
                    .values(booked_count=Event.booked_count - 1)
                )

        await self.db.commit()
        return BookingResponse.model_validate(booking)
