"""SQLAlchemy ORM models.

Data isolation: every user-owned row carries ``owner_id`` (directly or through its website/scan), and
every API query filters on the authenticated user's id. Organisations are not implemented; resources are
owned by individual users.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Incremented on password change / "log out everywhere"; embedded in JWTs to revoke old tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notify_scan_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_regressions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    websites: Mapped[list[Website]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Website(TimestampMixin, Base):
    __tablename__ = "websites"
    __table_args__ = (Index("ix_websites_owner_archived", "owner_id", "is_archived"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped[User] = relationship(back_populates="websites")
    scans: Mapped[list[Scan]] = relationship(back_populates="website", cascade="all, delete-orphan")
    monitoring: Mapped[MonitoringConfig | None] = relationship(
        back_populates="website", cascade="all, delete-orphan", uselist=False
    )


class Scan(TimestampMixin, Base):
    __tablename__ = "scans"
    __table_args__ = (
        Index("ix_scans_status_created", "status", "created_at"),
        Index("ix_scans_owner_created", "owner_id", "created_at"),
        Index("ix_scans_website_created", "website_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    website_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), nullable=False)
    # queued | running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="single", nullable=False)  # single | list | crawl
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual | schedule
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    pages_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    website: Mapped[Website] = relationship(back_populates="scans")
    pages: Mapped[list[ScanPage]] = relationship(back_populates="scan", cascade="all, delete-orphan")
    issues: Mapped[list[Issue]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class ScanPage(Base):
    __tablename__ = "scan_pages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)  # ok | failed | blocked
    http_status: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    lang: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    load_time_ms: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    violations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    incomplete_rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    inapplicable_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="pages")


class Issue(TimestampMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_issues_owner_status", "owner_id", "status"),
        Index("ix_issues_scan_impact", "scan_id", "impact"),
        Index("ix_issues_website_fingerprint", "website_id", "fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    website_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), nullable=False)
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    scan_page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scan_pages.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # violation | needs_review
    impact: Mapped[str] = mapped_column(String(20), default="minor", nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="other", nullable=False)
    wcag_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    wcag_level: Mapped[str] = mapped_column(String(5), default="", nullable=False)
    is_best_practice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    help: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    help_url: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    failure_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    selector: Mapped[str] = mapped_column(Text, default="", nullable=False)
    html_snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    page_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="axe-core", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # open | in_progress | marked_fixed | ignored
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    status_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    regressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="issues")
    notes: Mapped[list[IssueNote]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="IssueNote.created_at"
    )
    history: Mapped[list[IssueStatusHistory]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="IssueStatusHistory.created_at"
    )


class IssueNote(Base):
    __tablename__ = "issue_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    issue: Mapped[Issue] = relationship(back_populates="notes")


class IssueStatusHistory(Base):
    __tablename__ = "issue_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_status: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    issue: Mapped[Issue] = relationship(back_populates="history")


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AIRequestLog(Base):
    __tablename__ = "ai_request_logs"
    __table_args__ = (Index("ix_ai_logs_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScanComparison(Base):
    __tablename__ = "scan_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    website_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"))
    base_scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    target_scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | csv | docx
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MonitoringConfig(TimestampMixin, Base):
    __tablename__ = "monitoring_configs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="weekly", nullable=False)  # daily|weekly|monthly
    scan_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notify_on_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_regression: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    website: Mapped[Website] = relationship(back_populates="monitoring")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_owner_read", "owner_id", "is_read"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    detail: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
