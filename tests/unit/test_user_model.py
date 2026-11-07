from app.models.user import User, UserRole


def test_user_model_defaults() -> None:
    user = User(
        email="student@campushub.edu",
        hashed_password="hashed_secret_password",
        full_name="Dinmuhamed Sattarov",
        role=UserRole.STUDENT,
        is_active=True,
        is_verified=False,
    )

    assert user.email == "student@campushub.edu"
    assert user.full_name == "Dinmuhamed Sattarov"
    assert user.role == UserRole.STUDENT
    assert user.is_active is True
    assert user.is_verified is False
    assert UserRole.ORGANIZER.value == "ORGANIZER"
    assert UserRole.ADMIN.value == "ADMIN"
