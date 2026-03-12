"""
Authentication routes: register, login, profile.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.security import hash_password, verify_password, create_jwt
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    credits: float
    is_admin: bool


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Validate password strength
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == req.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.email.split("@")[0],
    )
    db.add(user)
    await db.flush()

    token = create_jwt(user.id, user.is_admin)
    return AuthResponse(
        token=token,
        user={"id": str(user.id), "email": user.email, "display_name": user.display_name},
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_jwt(user.id, user.is_admin)

    # Also set httponly cookie for frontend convenience
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,  # 24h
    )

    return AuthResponse(
        token=token,
        user={"id": str(user.id), "email": user.email, "display_name": user.display_name},
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/profile", response_model=ProfileResponse)
async def profile(user: User = Depends(get_current_user)):
    return ProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        credits=float(user.credits),
        is_admin=user.is_admin,
    )
