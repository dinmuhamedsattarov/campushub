from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
import pytest


async def _register_and_login(
    client: AsyncClient, email: str, role: str
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
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    return login_res.json()["access_token"]


@pytest.mark.asyncio
async def test_event_crud_search_filter_pagination_and_dashboard(
    client: AsyncClient,
) -> None:
    org_token = await _register_and_login(client, "org1@bme.hu", "ORGANIZER")
    org2_token = await _register_and_login(client, "org2@bme.hu", "ORGANIZER")
    student_token = await _register_and_login(client, "stud1@bme.hu", "STUDENT")

    now = datetime.now(timezone.utc)
    event_payload = {
        "title": "Blockchain Technology Workshop",
        "description": "Learn the fundamentals of distributed ledgers and smart contracts.",
        "category": "WORKSHOP",
        "location": "BME Building Q, Room QAF14",
        "start_time": (now + timedelta(days=3)).isoformat(),
        "end_time": (now + timedelta(days=3, hours=4)).isoformat(),
        "capacity": 50,
        "is_published": True,
    }

    # 1. Student cannot create an event (403 Forbidden)
    stud_create = await client.post(
        "/api/v1/events",
        json=event_payload,
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert stud_create.status_code == 403

    # 2. Organizer creates two events in different categories
    create_res1 = await client.post(
        "/api/v1/events",
        json=event_payload,
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert create_res1.status_code == 201
    event1 = create_res1.json()
    assert event1["available_spots"] == 50
    assert event1["booked_count"] == 0

    create_res2 = await client.post(
        "/api/v1/events",
        json={
            **event_payload,
            "title": "Cultural Night 2026",
            "description": "Evening of international student performances and food.",
            "category": "CULTURAL",
            "capacity": 150,
        },
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert create_res2.status_code == 201

    # 3. Search & Category Filtering + Pagination
    search_res = await client.get(
        "/api/v1/events", params={"search": "Blockchain", "page": 1, "size": 10}
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["title"] == "Blockchain Technology Workshop"

    cat_res = await client.get("/api/v1/events", params={"category": "CULTURAL"})
    assert cat_res.status_code == 200
    assert cat_res.json()["total"] == 1

    # 4. Ownership protection: Organizer 2 cannot update or delete Organizer 1's event
    forbidden_patch = await client.patch(
        f"/api/v1/events/{event1['id']}",
        json={"title": "Hacked Title"},
        headers={"Authorization": f"Bearer {org2_token}"},
    )
    assert forbidden_patch.status_code == 403

    # 5. Organizer 1 updates their own event
    patch_res = await client.patch(
        f"/api/v1/events/{event1['id']}",
        json={"capacity": 75},
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["capacity"] == 75
    assert patch_res.json()["available_spots"] == 75

    # 6. Organizer Dashboard endpoint
    dash_res = await client.get(
        "/api/v1/events/organizer/dashboard",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert dash["total_events"] == 2
    assert dash["total_capacity"] == 225
    assert dash["total_booked"] == 0
