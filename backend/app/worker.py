"""Background scan worker and monitoring scheduler.

Jobs live in the ``scans`` table (status ``queued``). A worker claims a job with an atomic
compare-and-set UPDATE (safe with several workers on PostgreSQL or SQLite), runs the browser scan,
commits every page in its own transaction and finalises the scan in one transaction at the end.

* Heartbeats are written while a scan runs. Scans whose heartbeat is older than
  ``WORKER_STALE_MINUTES`` (worker crash / restart) are re-queued once with their partial results
  removed, then marked failed - a scan never stays "running" forever.
* Concurrency is bounded by ``SCAN_MAX_CONCURRENCY`` per worker process.

Run standalone with ``python -m app.worker`` or embedded in the API process (``RUN_EMBEDDED_WORKER``).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update

from app.config import get_settings
from app.db import aware, session_factory, utcnow
from app.models import MonitoringConfig, Scan, Website
from app.scanner.engine import ScanEngine, ScanRequest, scanner_version
from app.services import (
    finalize_scan,
    log_activity,
    notify,
    persist_page,
    reset_scan_results,
)

log = logging.getLogger("accessiscan.worker")
MAX_ATTEMPTS = 2
FREQUENCIES = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30)}

EngineFactory = Callable[[], Any]


def next_run(frequency: str, from_time: Any = None) -> Any:
    return (from_time or utcnow()) + FREQUENCIES.get(frequency, FREQUENCIES["weekly"])


class Worker:
    def __init__(self, engine_factory: EngineFactory = ScanEngine) -> None:
        self.settings = get_settings()
        self.engine_factory = engine_factory
        self._sem = asyncio.Semaphore(self.settings.scan_max_concurrency)
        self._running: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ job claiming
    def claim_next(self) -> uuid.UUID | None:
        Session = session_factory()
        with Session() as db:
            candidates = db.scalars(
                select(Scan.id).where(Scan.status == "queued").order_by(Scan.created_at).limit(5)
            ).all()
            for scan_id in candidates:
                now = utcnow()
                res = db.execute(
                    update(Scan)
                    .where(Scan.id == scan_id, Scan.status == "queued")
                    .values(
                        status="running",
                        started_at=now,
                        heartbeat_at=now,
                        attempts=Scan.attempts + 1,
                        progress_message="Starting browser",
                    )
                )
                db.commit()
                if res.rowcount == 1:  # type: ignore[attr-defined]
                    return scan_id
        return None

    def recover_stale(self) -> int:
        cutoff = utcnow() - timedelta(minutes=self.settings.worker_stale_minutes)
        Session = session_factory()
        recovered = 0
        with Session() as db:
            stale = db.scalars(select(Scan).where(Scan.status == "running")).all()
            for scan in stale:
                hb = aware(scan.heartbeat_at) or aware(scan.started_at)
                if hb is not None and hb > cutoff:
                    continue
                reset_scan_results(db, scan)
                if scan.attempts < MAX_ATTEMPTS and not scan.cancel_requested:
                    scan.status, scan.progress_message, scan.pages_done = "queued", "Re-queued after interruption", 0
                else:
                    scan.status = "failed"
                    scan.error_message = "The scan was interrupted (worker restarted or timed out)"
                    scan.finished_at = utcnow()
                    notify(db, scan.owner_id, "scan_failed", "Scan failed", scan.error_message, f"/scans/{scan.id}")
                recovered += 1
            db.commit()
        return recovered

    def schedule_due(self) -> int:
        if not self.settings.scheduler_enabled:
            return 0
        Session = session_factory()
        created = 0
        now = utcnow()
        with Session() as db:
            due = db.scalars(
                select(MonitoringConfig).where(MonitoringConfig.enabled.is_(True), MonitoringConfig.next_run_at <= now)
            ).all()
            for cfg in due:
                site = db.get(Website, cfg.website_id)
                cfg.next_run_at = next_run(cfg.frequency, now)
                cfg.last_run_at = now
                if site is None or site.is_archived:
                    cfg.enabled = False
                    continue
                active = db.scalar(
                    select(Scan.id).where(Scan.website_id == site.id, Scan.status.in_(("queued", "running"))).limit(1)
                )
                if active is not None:
                    continue
                conf = {
                    "urls": [site.url],
                    "mode": "single",
                    "max_pages": 1,
                    "max_depth": 0,
                    "include_aaa": False,
                    "respect_robots": True,
                    **(cfg.scan_config or {}),
                }
                conf["urls"] = [site.url] if conf.get("mode") != "list" else conf.get("urls") or [site.url]
                db.add(
                    Scan(
                        owner_id=site.owner_id,
                        website_id=site.id,
                        mode=conf["mode"],
                        trigger="schedule",
                        config=conf,
                        pages_total=int(conf.get("max_pages", 1)),
                    )
                )
                log_activity(db, site.owner_id, "scan.scheduled", "website", site.id, site.url)
                created += 1
            db.commit()
        return created

    # ------------------------------------------------------------------ execution
    async def execute(self, scan_id: uuid.UUID) -> None:
        Session = session_factory()
        with Session() as db:
            scan = db.get(Scan, scan_id)
            if scan is None:
                return
            cfg = dict(scan.config or {})
            scan.scanner_version = scanner_version()
            db.commit()
        request = ScanRequest(
            urls=list(cfg.get("urls") or []),
            mode=str(cfg.get("mode", "single")),
            max_pages=int(cfg.get("max_pages", 1)),
            max_depth=int(cfg.get("max_depth", 0)),
            include_aaa=bool(cfg.get("include_aaa", False)),
            respect_robots=bool(cfg.get("respect_robots", True)),
        )

        async def on_page(result: Any, done: int) -> None:
            with Session() as db:
                scan = db.get(Scan, scan_id)
                if scan is None:
                    return
                persist_page(db, scan, result)
                scan.pages_done = done
                scan.heartbeat_at = utcnow()
                db.commit()

        async def should_cancel() -> bool:
            with Session() as db:
                scan = db.get(Scan, scan_id)
                if scan is None:
                    return True
                scan.heartbeat_at = utcnow()
                db.commit()
                return bool(scan.cancel_requested)

        async def on_progress(message: str, done: int, total: int) -> None:
            with Session() as db:
                db.execute(
                    update(Scan).where(Scan.id == scan_id).values(progress_message=message[:300], heartbeat_at=utcnow())
                )
                db.commit()

        try:
            outcome = await self.engine_factory().run(request, on_page, should_cancel, on_progress)
            with Session() as db:
                scan = db.get(Scan, scan_id)
                if scan is None:
                    return
                finalize_scan(db, scan, outcome)
                if scan.cancel_requested:
                    scan.status = "cancelled"
                scan.progress_message = ""
                db.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("scan %s failed", scan_id)
            with Session() as db:
                scan = db.get(Scan, scan_id)
                if scan is not None:
                    scan.status = "failed"
                    scan.error_message = _safe_error(exc)
                    scan.finished_at = utcnow()
                    scan.progress_message = ""
                    notify(db, scan.owner_id, "scan_failed", "Scan failed", scan.error_message, f"/scans/{scan.id}")
                    db.commit()

    async def _run_guarded(self, scan_id: uuid.UUID) -> None:
        async with self._sem:
            await self.execute(scan_id)

    async def run_once(self) -> int:
        """Claim and run all currently queued jobs (bounded concurrency). Used by tests and the CLI."""
        self.recover_stale()
        self.schedule_due()
        tasks = []
        while (scan_id := self.claim_next()) is not None:
            tasks.append(asyncio.create_task(self._run_guarded(scan_id)))
            if len(tasks) >= 50:
                break
        if tasks:
            await asyncio.gather(*tasks)
        return len(tasks)

    async def run_forever(self, stop: threading.Event | asyncio.Event) -> None:
        log.info("worker started (concurrency=%s)", self.settings.scan_max_concurrency)
        last_maintenance = 0.0
        loop = asyncio.get_running_loop()
        while not stop.is_set():
            try:
                if loop.time() - last_maintenance > 30:
                    await asyncio.to_thread(self.recover_stale)
                    await asyncio.to_thread(self.schedule_due)
                    last_maintenance = loop.time()
                self._running = {t for t in self._running if not t.done()}
                while len(self._running) < self.settings.scan_max_concurrency:
                    scan_id = await asyncio.to_thread(self.claim_next)
                    if scan_id is None:
                        break
                    self._running.add(asyncio.create_task(self._run_guarded(scan_id)))
            except Exception:  # noqa: BLE001 - database blips must not kill the worker
                log.exception("worker loop error")
            await asyncio.sleep(self.settings.worker_poll_seconds)
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)


def _safe_error(exc: Exception) -> str:
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    lowered = msg.lower()
    if "executable doesn't exist" in lowered or "playwright install" in lowered:
        return "The scanning browser is not installed on the server (run: python -m playwright install chromium)"
    return f"Scan error: {msg[:300]}"


def _new_loop() -> asyncio.AbstractEventLoop:
    # Playwright launches the browser as a subprocess, which on Windows requires the Proactor loop.
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


_embedded: tuple[threading.Thread, threading.Event] | None = None


def start_embedded_worker() -> None:
    global _embedded
    if _embedded is not None:
        return
    stop = threading.Event()

    def _target() -> None:
        with asyncio.Runner(loop_factory=_new_loop) as runner:
            runner.run(Worker().run_forever(stop))

    thread = threading.Thread(target=_target, name="accessiscan-worker", daemon=True)
    thread.start()
    _embedded = (thread, stop)


def stop_embedded_worker() -> None:
    global _embedded
    if _embedded is None:
        return
    thread, stop = _embedded
    stop.set()
    thread.join(timeout=10)
    _embedded = None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()

    def _stop(*_: Any) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    with asyncio.Runner(loop_factory=_new_loop) as runner:
        runner.run(Worker().run_forever(stop))


if __name__ == "__main__":
    main()
