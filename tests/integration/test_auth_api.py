from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_register_login_verify_and_me_flow(client: AsyncClient) -> None:
    # 1. Register a new student
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@bme.hu",
            "password": "StrongPassword123!",
            "full_name": "Dinmuhamed Sattarov",
            "role": "STUDENT",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["user"]["email"] == "student@bme.hu"
    assert reg_data["user"]["is_verified"] is False
    verification_token = reg_data["verification_token"]

    # 2. Verify email using the verification token
    verify_res = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["is_verified"] is True

    # 3. Login to receive JWT access + refresh tokens
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@bme.hu", "password": "StrongPassword123!"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # 4. Fetch /me profile with Bearer token
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "student@bme.hu"

    # 5. Refresh JWT tokens
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    assert "access_token" in refresh_res.json()


@pytest.mark.asyncio
async def test_role_based_access_control_permissions(client: AsyncClient) -> None:
    # Register & login a STUDENT
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "student2@bme.hu",
            "password": "StrongPassword123!",
            "full_name": "Student User",
            "role": "STUDENT",
        },
    )
    student_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "student2@bme.hu", "password": "StrongPassword123!"},
    )
    student_token = student_login.json()["access_token"]

    # Student attempting to hit organizer-only endpoint -> 403 Forbidden
    forbidden_res = await client.get(
        "/api/v1/auth/organizer-check",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert forbidden_res.status_code == 403

    # Register & login an ORGANIZER
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "organizer@bme.hu",
            "password": "StrongPassword123!",
            "full_name": "Organizer User",
            "role": "ORGANIZER",
        },
    )
    org_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "organizer@bme.hu", "password": "StrongPassword123!"},
    )
    org_token = org_login.json()["access_token"]

    # Organizer hitting organizer-only endpoint -> 200 OK
    allowed_res = await client.get(
        "/api/v1/auth/organizer-check",
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert allowed_res.status_code == 200
    assert allowed_res.json()["role"] == "ORGANIZER"
