"""
FastAPI application factory.

Startup sequence:
  1. Validate settings
  2. Check DB connectivity (warn on failure — do not crash, ALB will detect)
  3. Mount all API routers

Dev-mode notes:
  When DEV_SKIP_AUTH=true (development only):
    - A starlette middleware reads the X-Dev-User-ID header and sets a context
      variable so get_current_user() can look up the user without a Cognito token.
    - This middleware is NOT installed in staging/production.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import check_db_connection
from app.core.security import set_dev_cognito_sub
from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router
from app.api.v1.reference import router as reference_router

settings = get_settings()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG if settings.is_development else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting one-system backend (env=%s)", settings.environment)
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Database connection: OK")
    else:
        logger.warning("Database connection: FAILED — check DB_HOST / credentials")

    if settings.auth_disabled:
        logger.warning(
            "DEV_SKIP_AUTH=true — Cognito JWT verification is DISABLED. "
            "This must never be enabled in staging or production."
        )

    yield

    logger.info("Shutting down one-system backend")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rural Roads One System — API",
        version="0.2.0",
        description="Incident Management System backend API",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # CORS — restrict in production
    # ------------------------------------------------------------------ #
    origins = ["*"] if settings.is_development else [f"https://{settings.environment}.one-system.rrd.go.th"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # Dev-mode header middleware
    # ------------------------------------------------------------------ #
    if settings.auth_disabled:
        @app.middleware("http")
        async def dev_auth_middleware(request: Request, call_next):
            """
            Reads X-Dev-User-ID (a cognito_user_id string) and stores it
            in a context variable so get_current_user() can find the user.
            """
            dev_user_id = request.headers.get("X-Dev-User-ID")
            set_dev_cognito_sub(dev_user_id)
            response = await call_next(request)
            return response

    # ------------------------------------------------------------------ #
    # Global exception handler
    # ------------------------------------------------------------------ #
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #
    app.include_router(health_router)
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(reference_router, prefix="/api/v1")

    return app


app = create_app()
