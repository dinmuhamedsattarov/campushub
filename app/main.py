from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.auth.router import router as auth_router
from app.modules.bookings.router import router as bookings_router
from app.modules.events.router import router as events_router


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="University Event & Booking Platform — High-Concurrency Modular Monolith API",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth_router, prefix=settings.API_V1_STR)
    application.include_router(events_router, prefix=settings.API_V1_STR)
    application.include_router(bookings_router, prefix=settings.API_V1_STR)

    @application.get("/health", tags=["Reliability & Monitoring"])
    async def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "environment": settings.APP_ENV,
        }

    return application


app = create_application()
