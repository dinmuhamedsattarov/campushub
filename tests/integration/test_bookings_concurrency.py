import asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
import pytest


async def _create_user_and_token(
    client: AsyncClient, email: str, role: str = "STUDENT"
) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": f"User {email}",
            "role": role,
        },
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    return res.json()["access_token"]


async def _create_event(client: AsyncClient, org_token: str, capacity: int) -> str:
    now = datetime.now(timezone.utc)
    res = await client.post(
        "/api/v1/events",
        json={
            "title": "High Concurrency Systems Seminar",
            "description": "Deep dive into PostgreSQL locks and idempotency.",
            "category": "SEMINAR",
            "location": "Auditorium Maximum",
            "start_time": (now + timedelta(days=2)).isoformat(),
            "end_time": (now + timedelta(days=2, hours=2)).isoformat(),
            "capacity": capacity,
            "is_published": True,
        },
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert res.status_code == 201
    return res.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_key_prevents_duplicate_booking(client: AsyncClient) -> None:
    org_token = await _create_user_and_token(client, "org_idem@bme.hu", "ORGANIZER")
    student_token = await _create_user_and_token(client, "stud_idem@bme.hu", "STUDENT")
    event_id = await _create_event(client, org_token, capacity=5)

    headers = {
        "Authorization": f"Bearer {student_token}",
        "Idempotency-Key": "unique-network-retry-key-001",
    }

    # First request creates the booking
    res1 = await client.post(
        "/api/v1/bookings", json={"event_id": event_id}, headers=headers
    )
    assert res1.status_code == 201
    booking1 = res1.json()
    assert booking1["status"] == "CONFIRMED"
    assert booking1["qr_code_base64"] is not None

    # Second identical request (simulating network retry) returns the exact same booking
    res2 = await client.post(
        "/api/v1/bookings", json={"event_id": event_id}, headers=headers
    )
    assert res2.status_code == 201
    booking2 = res2.json()
    assert booking2["id"] == booking1["id"]
    assert booking2["ticket_code"] == booking1["ticket_code"]

    # Verify event booked_count is still 1 (not 2)
    event_res = await client.get(f"/api/v1/events/{event_id}")
    assert event_res.json()["booked_count"] == 1


@pytest.mark.asyncio
async def test_waitlist_and_automatic_promotion_on_cancel(client: AsyncClient) -> None:
    org_token = await _create_user_and_token(client, "org_wait@bme.hu", "ORGANIZER")
    s1_token = await _create_user_and_token(client, "s1_wait@bme.hu", "STUDENT")
    s2_token = await _create_user_and_token(client, "s2_wait@bme.hu", "STUDENT")
    event_id = await _create_event(client, org_token, capacity=1)

    # Student 1 takes the only seat -> CONFIRMED
    b1_res = await client.post(
        "/api/v1/bookings",
        json={"event_id": event_id},
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert b1_res.status_code == 201
    b1 = b1_res.json()
    assert b1["status"] == "CONFIRMED"

    # Student 2 joins waitlist -> WAITLISTED (position 1)
    b2_res = await client.post(
        "/api/v1/bookings",
        json={"event_id": event_id, "join_waitlist_if_full": True},
        headers={"Authorization": f"Bearer {s2_token}"},
    )
    assert b2_res.status_code == 201
    b2 = b2_res.json()
    assert b2["status"] == "WAITLISTED"
    assert b2["waitlist_position"] == 1

    # Student 1 cancels -> Student 2 is automatically promoted to CONFIRMED with QR code
    cancel_res = await client.post(
        f"/api/v1/bookings/{b1['id']}/cancel",
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    s2_bookings = await client.get(
        "/api/v1/bookings/my",
        headers={"Authorization": f"Bearer {s2_token}"},
    )
    promoted = s2_bookings.json()[0]
    assert promoted["status"] == "CONFIRMED"
    assert promoted["qr_code_base64"] is not None


@pytest.mark.asyncio
async def test_100_concurrent_requests_for_last_seat_prevents_overbooking(
    client: AsyncClient,
) -> None:
    org_token = await _create_user_and_token(client, "org_race@bme.hu", "ORGANIZER")
    # Event has ONLY 1 SEAT available!
    event_id = await _create_event(client, org_token, capacity=1)

    # Register 100 distinct students
    tokens: list[str] = []
    for i in range(100):
        t = await _create_user_and_token(client, f"racer_{i}@bme.hu", "STUDENT")
        tokens.append(t)

    # Fire 100 simultaneous booking requests for the single remaining seat
    async def attempt_booking(token: str) -> int:
        resp = await client.post(
            "/api/v1/bookings",
            json={"event_id": event_id, "join_waitlist_if_full": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.status_code

    statuses = await asyncio.gather(*(attempt_booking(t) for t in tokens))

    # Exactly 1 request must succeed (201 Created), and 99 must fail with 409 Conflict
    assert statuses.count(201) == 1
    assert statuses.count(409) == 99

    # Verify event booked_count is strictly 1 and available_spots is 0
    event_res = await client.get(f"/api/v1/events/{event_id}")
    event_data = event_res.json()
    assert event_data["booked_count"] == 1
    assert event_data["available_spots"] == 0
