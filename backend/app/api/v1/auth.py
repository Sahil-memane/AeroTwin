from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.core.security import verify_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate a user and return JWT tokens.
    Rate-limited to 5 attempts per minute per IP.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=423, detail="Account locked or inactive")

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=60 * 24 * 8 * 60,  # 8 days in seconds
        role=user.role,
    )


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Validate a refresh token and issue a new access token."""
    current_user = await get_current_user(db=db, token=req.refresh_token)
    access_token = create_access_token(subject=str(current_user.id))
    return {
        "access_token": access_token,
        "expires_in": 60 * 24 * 8 * 60,
    }
