from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    get_user_from_refresh_token,
)
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
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=60 * 24 * 8 * 60,  # 8 days in seconds
        role=user.role,
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "operator"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Self-service registration. Creates an operator account and returns tokens.
    Rate-limited to 3 attempts per minute per IP.
    """
    # Validate role — only safe self-service roles allowed
    allowed_roles = {"operator", "maintenance_engineer", "program_manager"}
    if req.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role must be one of: {', '.join(sorted(allowed_roles))}",
        )

    # Password strength check (min 12 chars enforced server-side too)
    if len(req.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 12 characters.",
        )

    # Check for duplicate email
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    new_user = User(
        email=req.email,
        hashed_password=get_password_hash(req.password),
        role=req.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(subject=str(new_user.id))
    refresh_token = create_refresh_token(subject=str(new_user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=60 * 24 * 8 * 60,
        role=new_user.role,
    )


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh(request: Request, req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Validate a refresh token (rejecting an access token) and issue a new access token."""
    current_user = await get_user_from_refresh_token(db=db, token=req.refresh_token)
    access_token = create_access_token(subject=str(current_user.id))
    return {
        "access_token": access_token,
        "expires_in": 60 * 24 * 8 * 60,
    }
