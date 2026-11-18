"""Authentication and account endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.config import get_settings
from app.db import utcnow
from app.deps import DB, CurrentUser, client_ip
from app.models import User
from app.ratelimit import SlidingWindowLimiter
from app.schemas import (
    DeleteAccountIn,
    LoginIn,
    PasswordChange,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserOut,
    UserUpdate,
)
from app.security import (
    create_access_token,
    hash_password,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from app.services import log_activity

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/users", tags=["users"])

login_limiter = SlidingWindowLimiter(limit=get_settings().login_attempts_per_15min, window_seconds=15 * 60)
register_limiter = SlidingWindowLimiter(limit=10, window_seconds=60 * 60)


def _tokens(db: DB, user: User) -> TokenOut:
    access, expires = create_access_token(user)
    refresh = issue_refresh_token(db, user)
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=expires)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DB, request: Request) -> TokenOut:
    if not get_settings().registration_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled on this server")
    if not register_limiter.hit(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many registrations. Try again later")
    email = body.email.lower().strip()
    if db.scalar(select(func.count()).select_from(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this e-mail address already exists")
    user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    log_activity(db, user.id, "account.registered", "user", user.id)
    return _tokens(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DB, request: Request) -> TokenOut:
    email = body.email.lower().strip()
    if not login_limiter.hit(f"{client_ip(request)}|{email}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Wait 15 minutes and try again")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect e-mail address or password")
    user.last_login_at = utcnow()
    log_activity(db, user.id, "account.login", "user", user.id)
    return _tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: DB) -> TokenOut:
    rotated = rotate_refresh_token(db, body.refresh_token)
    if rotated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again")
    user, new_refresh = rotated
    access, expires = create_access_token(user)
    return TokenOut(access_token=access, refresh_token=new_refresh, expires_in=expires)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: DB) -> Response:
    revoke_refresh_token(db, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, db: DB) -> Response:
    user.token_version += 1
    revoke_all_refresh_tokens(db, user.id)
    log_activity(db, user.id, "account.logout_all", "user", user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@me_router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdate, user: CurrentUser, db: DB) -> User:
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    log_activity(db, user.id, "account.updated", "user", user.id)
    db.commit()
    return user


@me_router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user: CurrentUser, db: DB) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # invalidates all existing access tokens
    revoke_all_refresh_tokens(db, user.id)
    log_activity(db, user.id, "account.password_changed", "user", user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(body: DeleteAccountIn, user: CurrentUser, db: DB) -> Response:
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The password is incorrect")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
