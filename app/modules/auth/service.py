import uuid

from fastapi import HTTPException, status
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.modules.auth.schemas import (
    RegistrationResponse,
    TokenPairResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def register_user(self, payload: UserRegisterRequest) -> RegistrationResponse:
        existing_user = await self.get_user_by_email(payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address is already registered.",
            )

        user = User(
            email=payload.email.lower(),
            hashed_password=get_password_hash(payload.password),
            full_name=payload.full_name,
            role=payload.role,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        verification_token = create_email_verification_token(user.email)
        return RegistrationResponse(
            user=UserResponse.model_validate(user),
            verification_token=verification_token,
        )

    async def authenticate_user(self, payload: UserLoginRequest) -> TokenPairResponse:
        user = await self.get_user_by_email(payload.email)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated.",
            )

        return TokenPairResponse(
            access_token=create_access_token(user.id, user.role.value),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPairResponse:
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type. Expected refresh token.",
                )
            user_id = uuid.UUID(payload["sub"])
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            ) from exc

        user = await self.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive.",
            )

        return TokenPairResponse(
            access_token=create_access_token(user.id, user.role.value),
            refresh_token=create_refresh_token(user.id),
        )

    async def verify_email(self, token: str) -> UserResponse:
        try:
            payload = decode_token(token)
            if payload.get("type") != "verify_email":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid verification token type.",
                )
            email: str = payload["sub"]
        except (jwt.PyJWTError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired email verification token.",
            ) from exc

        user = await self.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        user.is_verified = True
        await self.db.commit()
        await self.db.refresh(user)
        return UserResponse.model_validate(user)
