from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole
from app.modules.auth.dependencies import get_current_user, require_roles
from app.modules.auth.schemas import (
    EmailVerificationRequest,
    RegistrationResponse,
    TokenPairResponse,
    TokenRefreshRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["1. Authentication & Authorization"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegistrationResponse:
    return await AuthService(db).register_user(payload)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    return await AuthService(db).authenticate_user(payload)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_access_token(
    payload: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    return await AuthService(db).refresh_tokens(payload.refresh_token)


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    payload: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    return await AuthService(db).verify_email(payload.token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/organizer-check", response_model=dict[str, str])
async def organizer_only_check(
    current_user: User = Depends(require_roles(UserRole.ORGANIZER, UserRole.ADMIN)),
) -> dict[str, str]:
    return {
        "status": "authorized",
        "email": current_user.email,
        "role": current_user.role.value,
    }
