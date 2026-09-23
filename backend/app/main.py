from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api.v1 import auth, engines, users, uav_assets, missions, dashboard

# ── Rate Limiter ──
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ──
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
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


# ── Health Check ──
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
