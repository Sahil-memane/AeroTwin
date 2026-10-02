import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api.v1 import (
    auth, engines, users, uav_assets, missions, dashboard,
    faults, bearing, telemetry, maintenance, models, alerts, copilot, auxiliary, simulation,
    simulator_control,
)
from app.services.ingestion import ingestion_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Rate Limiter ──
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan (startup / shutdown) ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("Starting MQTT ingestion service…")
    await ingestion_service.start()
    yield
    # ── Shutdown ──
    logger.info("Stopping MQTT ingestion service…")
    await ingestion_service.stop()


# ── FastAPI App ──
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──
# allow_credentials=True + allow_origins=["*"] is spec-invalid (browsers
# won't honor a wildcard origin alongside credentialed requests) and was
# never actually needed here — auth is a Bearer token in the Authorization
# header via localStorage, not a cookie, so no request this API serves
# relies on the browser's credentials mode at all.
settings.assert_production_safe()  # no-op unless ENVIRONMENT=production

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # "*" by default in development; explicit list in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
prefix = settings.API_V1_STR

app.include_router(auth.router,       prefix=f"{prefix}/auth",       tags=["auth"])
app.include_router(users.router,      prefix=f"{prefix}/users",      tags=["users"])
app.include_router(uav_assets.router, prefix=f"{prefix}/uav-assets", tags=["uav-assets"])
app.include_router(engines.router,    prefix=f"{prefix}/engines",    tags=["engines"])
app.include_router(missions.router,   prefix=f"{prefix}/missions",   tags=["missions"])
app.include_router(dashboard.router,  prefix=f"{prefix}/dashboard",  tags=["dashboard"])
app.include_router(faults.router,      prefix=f"{prefix}/engines",  tags=["faults"])
app.include_router(bearing.router,     prefix=f"{prefix}/engines",  tags=["bearing"])
app.include_router(auxiliary.router,   prefix=f"{prefix}/engines",  tags=["aux"])
app.include_router(maintenance.router, prefix=f"{prefix}/engines",  tags=["maintenance"])
app.include_router(telemetry.router,   prefix=prefix,               tags=["telemetry"])
app.include_router(models.router,      prefix=f"{prefix}/models",   tags=["models"])
app.include_router(alerts.router,      prefix=f"{prefix}/alerts",   tags=["alerts"])
app.include_router(copilot.router,           prefix=f"{prefix}/copilot",    tags=["copilot"])
app.include_router(simulation.router,        prefix=f"{prefix}/simulation",  tags=["simulation"])
app.include_router(simulator_control.router, prefix=f"{prefix}/simulator",   tags=["simulator-control"])


# ── Health Check ──
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
