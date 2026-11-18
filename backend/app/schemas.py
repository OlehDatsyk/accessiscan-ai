"""Pydantic v2 request/response models for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- auth / users
def _password_rules(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(v) > 128:
        raise ValueError("Password must be at most 128 characters")
    if v.lower() == v or v.upper() == v or not any(c.isdigit() for c in v):
        raise ValueError("Password must contain upper- and lower-case letters and a number")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(default="", max_length=200)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _password_rules(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    notify_scan_complete: bool
    notify_regressions: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    notify_scan_complete: bool | None = None
    notify_regressions: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _password_rules(v)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=256)


# ----------------------------------------------------------------------------- websites
class WebsiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    description: str = Field(default="", max_length=2000)


class WebsiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None


class WebsiteOut(ORM):
    id: uuid.UUID
    name: str
    url: str
    description: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    latest_score: float | None = None
    latest_scan_id: uuid.UUID | None = None
    latest_scan_at: datetime | None = None
    latest_scan_status: str | None = None
    scan_count: int = 0
    open_violations: int = 0
    monitoring_enabled: bool = False


# ----------------------------------------------------------------------------- scans
class ScanCreate(BaseModel):
    website_id: uuid.UUID
    mode: Literal["single", "list", "crawl"] = "single"
    urls: list[str] = Field(default_factory=list, max_length=50)
    max_pages: int = Field(default=5, ge=1, le=50)
    max_depth: int = Field(default=1, ge=0, le=5)
    include_aaa: bool = False
    respect_robots: bool = True


class ScanOut(ORM):
    id: uuid.UUID
    website_id: uuid.UUID
    status: str
    mode: str
    trigger: str
    config: dict[str, Any]
    pages_total: int
    pages_done: int
    progress_message: str
    score: float | None
    summary: dict[str, Any]
    scanner_version: str
    error_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    website_name: str | None = None
    website_url: str | None = None


class ScanPageOut(ORM):
    id: uuid.UUID
    url: str
    final_url: str
    depth: int
    status: str
    http_status: int | None
    title: str
    lang: str
    error: str
    load_time_ms: int | None
    score: float | None
    violations_count: int
    needs_review_count: int
    passed_rules: list[str]
    incomplete_rules: list[str]
    inapplicable_count: int
    page_metadata: dict[str, Any]


# ----------------------------------------------------------------------------- issues
class IssueOut(ORM):
    id: uuid.UUID
    scan_id: uuid.UUID
    website_id: uuid.UUID
    scan_page_id: uuid.UUID
    rule_id: str
    kind: str
    impact: str
    category: str
    wcag_criteria: list[str]
    wcag_level: str
    is_best_practice: bool
    description: str
    help: str
    help_url: str
    failure_summary: str
    selector: str
    html_snippet: str
    page_url: str
    source: str
    fingerprint: str
    status: str
    status_reason: str
    regressed: bool
    created_at: datetime
    updated_at: datetime


class NoteOut(ORM):
    id: uuid.UUID
    body: str
    author_id: uuid.UUID
    created_at: datetime


class HistoryOut(ORM):
    id: uuid.UUID
    from_status: str
    to_status: str
    reason: str
    actor_id: uuid.UUID | None
    created_at: datetime


class IssueDetail(IssueOut):
    notes: list[NoteOut] = []
    history: list[HistoryOut] = []
    wcag_details: list[dict[str, Any]] = []
    guidance: dict[str, Any] | None = None
    ai_suggestion: dict[str, Any] | None = None


class IssueStatusIn(BaseModel):
    status: Literal["open", "in_progress", "marked_fixed", "ignored"]
    reason: str = Field(default="", max_length=2000)


class BulkStatusIn(IssueStatusIn):
    issue_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


# ----------------------------------------------------------------------------- misc
class ContrastIn(BaseModel):
    foreground: str = Field(max_length=40)
    background: str = Field(max_length=40)


class AskIn(BaseModel):
    scan_id: uuid.UUID
    question: str = Field(min_length=3, max_length=2000)
    issue_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class ReportCreate(BaseModel):
    scan_id: uuid.UUID
    format: Literal["pdf", "csv", "docx"]


class ReportOut(ORM):
    id: uuid.UUID
    scan_id: uuid.UUID
    format: str
    filename: str
    size_bytes: int
    created_at: datetime


class MonitoringIn(BaseModel):
    enabled: bool
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    mode: Literal["single", "crawl"] = "single"
    max_pages: int = Field(default=1, ge=1, le=50)
    max_depth: int = Field(default=0, ge=0, le=5)
    notify_on_complete: bool = True
    notify_on_regression: bool = True


class MonitoringOut(ORM):
    id: uuid.UUID
    website_id: uuid.UUID
    enabled: bool
    frequency: str
    scan_config: dict[str, Any]
    notify_on_complete: bool
    notify_on_regression: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    website_name: str | None = None
    website_url: str | None = None


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str
    is_read: bool
    created_at: datetime
