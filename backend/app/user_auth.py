
"""
RAYMOND v2.8 — User Authentication Foundation

Features:
- User registration and login
- Scrypt password hashing
- HMAC-SHA256 signed bearer tokens
- 12-hour token expiry
- Authenticated /me endpoint

Security notes:
- Plaintext passwords are never stored.
- Password hashes and token secrets are never returned.
- RAYMOND_USER_AUTH_SECRET must be configured on the backend.
- This module does not execute broker orders.
- Broker-account ownership enforcement is a separate required step.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import Base, get_db
except ImportError:
    from database import Base, get_db


# ============================================================
# ROUTER AND SETTINGS
# ============================================================

router = APIRouter(
    prefix="/api/auth",
    tags=["User Authentication"],
)

bearer_scheme = HTTPBearer(auto_error=False)

TOKEN_TTL_SECONDS = 12 * 60 * 60

PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
PASSWORD_SALT_BYTES = 16
PASSWORD_KEY_BYTES = 32


# ============================================================
# DATABASE MODEL
# ============================================================

class User(Base):
    __tablename__ = "raymond_users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
    )

    email = Column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash = Column(
        String(512),
        nullable=False,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


# ============================================================
# REQUEST AND RESPONSE SCHEMAS
# ============================================================

class RegisterRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
    )

    password: str = Field(
        min_length=12,
        max_length=256,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()

        # Basic syntax check without an additional dependency.
        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.fullmatch(pattern, value):
            raise ValueError("Enter a valid email address.")

        return value


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
    )

    password: str = Field(
        min_length=1,
        max_length=256,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()

        if not re.fullmatch(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            value,
        ):
            raise ValueError("Enter a valid email address.")

        return value


class UserResponse(BaseModel):
    user_id: str
    email: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# ============================================================
# BACKEND SECRET
# ============================================================

def _token_secret() -> bytes:
    """
    Read the token-signing secret from the backend environment.

    Never place this secret in Flutter or commit it to GitHub.
    """

    secret = os.getenv(
        "RAYMOND_USER_AUTH_SECRET",
        "",
    )

    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "User authentication is not configured. "
                "Set RAYMOND_USER_AUTH_SECRET in the backend "
                "environment to a random secret of at least "
                "32 characters."
            ),
        )

    return secret.encode("utf-8")


# ============================================================
# PASSWORD HASHING
# ============================================================

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)

    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
        dklen=PASSWORD_KEY_BYTES,
    )

    salt_text = base64.urlsafe_b64encode(
        salt
    ).decode("ascii")

    key_text = base64.urlsafe_b64encode(
        derived_key
    ).decode("ascii")

    return (
        f"scrypt${PASSWORD_SCRYPT_N}"
        f"${salt_text}${key_text}"
    )


def _verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    try:
        algorithm, n_text, salt_text, key_text = (
            stored_hash.split("$", 3)
        )

        if algorithm != "scrypt":
            return False

        n = int(n_text)

        # Do not allow database contents to choose arbitrary
        # expensive hashing parameters.
        if n != PASSWORD_SCRYPT_N:
            return False

        salt = base64.urlsafe_b64decode(
            salt_text.encode("ascii")
        )

        expected_key = base64.urlsafe_b64decode(
            key_text.encode("ascii")
        )

        if len(salt) != PASSWORD_SALT_BYTES:
            return False

        if len(expected_key) != PASSWORD_KEY_BYTES:
            return False

        actual_key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=PASSWORD_SCRYPT_N,
            r=PASSWORD_SCRYPT_R,
            p=PASSWORD_SCRYPT_P,
            dklen=PASSWORD_KEY_BYTES,
        )

        return hmac.compare_digest(
            actual_key,
            expected_key,
        )

    except (
        ValueError,
        TypeError,
        UnicodeError,
    ):
        return False


# ============================================================
# TOKEN ENCODING
# ============================================================

def _b64url_encode(data: bytes) -> str:
    return (
        base64.urlsafe_b64encode(data)
        .rstrip(b"=")
        .decode("ascii")
    )


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    return base64.urlsafe_b64decode(
        (value + padding).encode("ascii")
    )


def _create_access_token(user: User) -> str:
    now = int(time.time())

    payload = {
        "sub": user.user_id,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(16),
    }

    encoded_payload = _b64url_encode(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    signature = hmac.new(
        _token_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()

    return (
        encoded_payload
        + "."
        + _b64url_encode(signature)
    )


def _decode_access_token(token: str) -> dict:
    try:
        if len(token) > 8192:
            raise ValueError("Token too large.")

        encoded_payload, encoded_signature = (
            token.split(".", 1)
        )

        expected_signature = hmac.new(
            _token_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()

        supplied_signature = _b64url_decode(
            encoded_signature
        )

        if not hmac.compare_digest(
            expected_signature,
            supplied_signature,
        ):
            raise ValueError("Invalid signature.")

        payload = json.loads(
            _b64url_decode(
                encoded_payload
            ).decode("utf-8")
        )

        if not isinstance(payload, dict):
            raise ValueError("Invalid token payload.")

        subject = payload.get("sub")
        issued_at = payload.get("iat")
        expires_at = payload.get("exp")

        if not isinstance(subject, str) or not subject:
            raise ValueError("Invalid subject.")

        if not isinstance(issued_at, int):
            raise ValueError("Invalid issue time.")

        if not isinstance(expires_at, int):
            raise ValueError("Invalid expiry.")

        now = int(time.time())

        if issued_at > now + 60:
            raise ValueError("Token issued in the future.")

        if expires_at <= now:
            raise ValueError("Token expired.")

        if expires_at <= issued_at:
            raise ValueError("Invalid token lifetime.")

        if expires_at - issued_at > TOKEN_TTL_SECONDS:
            raise ValueError("Token lifetime exceeds limit.")

        return payload

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )


# ============================================================
# AUTHENTICATED USER DEPENDENCY
# ============================================================

def get_current_user(
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported authentication scheme.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    payload = _decode_access_token(
        credentials.credentials
    )

    user = (
        db.query(User)
        .filter(
            User.user_id == payload["sub"]
        )
        .first()
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return user


# ============================================================
# SAFE USER SERIALIZATION
# ============================================================

def _serialize_user(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=_create_access_token(user),
        token_type="bearer",
        expires_in=TOKEN_TTL_SECONDS,
        user=_serialize_user(user),
    )


# ============================================================
# REGISTER
# ============================================================

@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    # Fail closed if the backend secret is not configured.
    _token_secret()

    existing_user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        user_id=secrets.token_hex(18),
        email=request.email,
        password_hash=_hash_password(
            request.password
        ),
        is_active=True,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        # Covers concurrent registration attempts for the
        # same email address.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    except Exception:
        db.rollback()
        raise

    return _auth_response(user)


# ============================================================
# LOGIN
# ============================================================

@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    _token_secret()

    user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    # Do not disclose whether the email exists.
    if (
        user is None
        or not _verify_password(
            request.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled.",
        )

    return _auth_response(user)


# ============================================================
# CURRENT USER
# ============================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return _serialize_user(current_user)
