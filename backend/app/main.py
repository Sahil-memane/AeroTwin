from fastapi import FastAPI
from app.core.config import settings
from app.api.v1 import auth, engines

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(engines.router, prefix=f"{settings.API_V1_STR}/engines", tags=["engines"])

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
