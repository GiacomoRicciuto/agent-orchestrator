"""
Authentication and encryption utilities.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.config import get_settings


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── JWT Tokens ───────────────────────────────────────────────────────────────

def create_jwt(user_id: uuid.UUID, is_admin: bool = False) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ── Fernet Encryption (for customer API keys at rest) ────────────────────────

def _get_fernet() -> Fernet:
    settings = get_settings()
    if not settings.fernet_key:
        raise RuntimeError("FERNET_KEY not configured. Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    return Fernet(settings.fernet_key.encode())


def encrypt_data(data: str) -> bytes:
    """Encrypt a string (e.g., JSON of API keys) → bytes for DB storage."""
    return _get_fernet().encrypt(data.encode())


def decrypt_data(encrypted: bytes) -> str:
    """Decrypt bytes from DB → original string."""
    return _get_fernet().decrypt(encrypted).decode()
