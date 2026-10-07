import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.core import config
from app.db import seed
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.auth.router import router as auth_router
from app.modules.billing import service as billing_service
from app.modules.billing.router import router as billing_router
from app.modules.dashboard.router import router as dashboard_router
from app.db.engine import DatabaseUnavailable, close_db, init_db, redacted_url
from app.modules.medicines.router import router as medicine_router
from app.modules.patients.router import router as patient_router
from app.modules.pos.service import CheckoutError
from app.modules.pos.router import router as pos_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("app.main")


SESSION_CLEANUP_INTERVAL_SECONDS = 3600


async def _clean_expired_sessions():
    """Deletes sessions past their absolute expiry once an hour (idle ones also go on lookup)."""
    while True:
        try:
            removed = await auth_service.delete_expired_sessions()
            if removed:
                logger.info(f"Removed {removed} expired sessions")
        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fails fast with a clear error if PostgreSQL can't be reached or the schema isn't migrated
    await init_db()
    if config.SEED_DEMO_DATA:
        await seed.seed_database()
    else:
        logger.info("Demo data disabled (SEED_DEMO_DATA=false)")
    await auth_service.bootstrap_admin()
    cleanup = asyncio.create_task(_clean_expired_sessions())
    yield
    cleanup.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup
    await close_db()


app = FastAPI(
    title="PharmaCore API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.ENABLE_DOCS else None,
    redoc_url="/redoc" if config.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
)

# The bundled frontend is served from the same origin, so cross-origin access is
# opt-in via CORS_ORIGINS. Never combine a wildcard origin with credentials.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", config.CSRF_HEADER_NAME],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        # API responses carry patient and billing data: never cache them
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Service errors -> HTTP responses, in one place instead of try/except in every view
def _error(status_code: int):
    async def handler(_: Request, exc: Exception):
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})
    return handler


app.add_exception_handler(billing_service.InvoiceError, _error(status.HTTP_400_BAD_REQUEST))
app.add_exception_handler(CheckoutError, _error(status.HTTP_400_BAD_REQUEST))
app.add_exception_handler(auth_service.AuthUnavailable, _error(status.HTTP_503_SERVICE_UNAVAILABLE))
app.add_exception_handler(DatabaseUnavailable, _error(status.HTTP_503_SERVICE_UNAVAILABLE))


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    # Safety net: the services validate first, the database constraints are the backstop
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(getattr(exc.orig, "__cause__", None), "sqlstate", None)
    logger.warning(f"Integrity error ({sqlstate}): {exc.orig}")
    if sqlstate == "23505":
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": "This record already exists."})
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": "The change violates a data rule and was not saved."})


# Public: login / logout / session endpoints (each enforces its own checks)
app.include_router(auth_router, prefix="/api", tags=["Auth"])

# Everything else requires an authenticated session
protected = [Depends(get_current_user)]
app.include_router(medicine_router, prefix="/api", tags=["Medicine"], dependencies=protected)
app.include_router(patient_router, prefix="/api", tags=["Patient"], dependencies=protected)
app.include_router(pos_router, prefix="/api/pos", tags=["POS"], dependencies=protected)
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"], dependencies=protected)
app.include_router(billing_router, prefix="/api", tags=["Billing"], dependencies=protected)


class DemoResetRequest(BaseModel):
    confirm: str = Field(max_length=100)


class DemoSeedStatus(BaseModel):
    status: str | None = None
    version: int | None = None
    completed_at: object | None = None


class SystemStatus(BaseModel):
    status: str
    database_url: str
    demo_data: DemoSeedStatus
    demo_reset_enabled: bool
    demo_reset_confirmation: str


@app.post("/api/settings/seed", tags=["Settings"])
async def reset_and_seed_db(body: DemoResetRequest, request: Request, admin: dict = Depends(require_admin)):
    """Deletes ALL business data (patients, prescriptions, stock, invoices...) and reloads demo data."""
    if not config.ALLOW_DEMO_RESET:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Demo data reset is disabled on this server (ALLOW_DEMO_RESET=false).")
    if body.confirm.strip() != config.DEMO_RESET_CONFIRMATION:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f'Type "{config.DEMO_RESET_CONFIRMATION}" exactly to confirm the reset.')

    ip = request.client.host if request.client else ""
    logger.warning(f"Demo data reset requested by {admin['email']}")
    await auth_service.record_event("demo_reset_started", email=admin["email"], user_id=admin["id"], ip=ip)
    await seed.seed_database(force_reset=True)
    await auth_service.record_event("demo_reset_completed", email=admin["email"], user_id=admin["id"], ip=ip)
    return {"status": "success", "message": "All business data was deleted and demo data reloaded."}


@app.get("/api/settings/status", response_model=SystemStatus, tags=["Settings"])
async def get_db_status(_: dict = Depends(get_current_user)):
    return {
        "status": "online",
        "database_url": redacted_url(),  # never includes the password
        "demo_data": await seed.demo_seed_status(),
        "demo_reset_enabled": config.ALLOW_DEMO_RESET,
        "demo_reset_confirmation": config.DEMO_RESET_CONFIRMATION,
    }


@app.get("/")
async def root():
    return {"message": "PharmaCore Enterprise PMS API is running"}
