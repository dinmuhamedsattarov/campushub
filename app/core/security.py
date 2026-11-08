from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Argon2."""
    return password_hash.hash(password)


def create_token(
    subject: str | uuid.UUID,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT token with type ('access', 'refresh', or 'verify_email')."""
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    return create_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"role": role},
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return create_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_email_verification_token(email: str) -> str:
    return create_token(
        subject=email,
        token_type="verify_email",
        expires_delta=timedelta(hours=24),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises jwt.PyJWTError if invalid/expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
