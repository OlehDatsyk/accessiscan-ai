"""Password hashing (Argon2id), JWT access tokens and rotating refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import aware, utcnow
from app.models import RefreshToken, User

_hasher = PasswordHasher()  # argon2id with library defaults (memory-hard)
JWT_ALG = "HS256"
JWT_AUDIENCE = "accessiscan-api"
JWT_ISSUER = "accessiscan"

# A precomputed hash used to keep login timing similar for unknown e-mail addresses.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_minutes * 60
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "ver": user.token_version,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=expires_in),
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALG), expires_in


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[JWT_ALG],  # explicit allow-list: rejects "none" and algorithm confusion
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_refresh_token(db: Session, user: User, family_id: uuid.UUID | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=_hash_token(raw),
            expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    return raw


def rotate_refresh_token(db: Session, raw: str) -> tuple[User, str] | None:
    """Exchange a refresh token for a new one. Reuse of a revoked token revokes the whole family."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash_token(raw)))
    if row is None:
        return None
    now = utcnow()
    if row.revoked_at is not None:
        # Token reuse detected: someone replayed an already-rotated token. Kill the family.
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        return None
    if (aware(row.expires_at) or now) <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.revoked_at = now
    new_raw = issue_refresh_token(db, user, family_id=row.family_id)
    db.commit()
    return user, new_raw


def revoke_refresh_token(db: Session, raw: str) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash_token(raw)))
    if row is not None and row.revoked_at is None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        db.commit()


def revoke_all_refresh_tokens(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
