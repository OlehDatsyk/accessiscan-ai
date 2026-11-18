"""FastAPI dependencies: database session, authenticated user, ownership lookups."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Issue, Scan, User, Website
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def get_current_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    payload = decode_access_token(creds.credentials)
    if payload is None:
        raise unauthorized
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def not_found(what: str = "Resource") -> HTTPException:
    # 404 (not 403) for other users' resources so that IDs cannot be probed.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def get_owned_website(db: Session, user: User, website_id: uuid.UUID) -> Website:
    site = db.scalar(select(Website).where(Website.id == website_id, Website.owner_id == user.id))
    if site is None:
        raise not_found("Website")
    return site


def get_owned_scan(db: Session, user: User, scan_id: uuid.UUID) -> Scan:
    scan = db.scalar(select(Scan).where(Scan.id == scan_id, Scan.owner_id == user.id))
    if scan is None:
        raise not_found("Scan")
    return scan


def get_owned_issue(db: Session, user: User, issue_id: uuid.UUID) -> Issue:
    issue = db.scalar(select(Issue).where(Issue.id == issue_id, Issue.owner_id == user.id))
    if issue is None:
        raise not_found("Issue")
    return issue


def client_ip(request: Request) -> str:
    if get_settings().trusted_proxy_headers:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
