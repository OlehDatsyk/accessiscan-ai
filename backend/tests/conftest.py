"""Test configuration.

* Every test gets a fresh SQLite database (set TEST_DATABASE_URL to run against PostgreSQL instead).
* DNS is faked: no test touches the internet. Unknown names resolve to a public documentation-free
  address so API-level URL validation succeeds without network access.
* ``site`` serves the local fixture website (pages with known violations / known passing pages) and
  ``internal`` is a second local server that plays the role of an internal service which the scanner
  must never reach. It counts every request it receives.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-0123456789",
        "RUN_EMBEDDED_WORKER": "false",
        "SCAN_CRAWL_DELAY_MS": "0",
        "AI_PROVIDER": "none",
        "SCHEDULER_ENABLED": "true",
        "SCAN_USER_HOURLY_LIMIT": "100",
        "SCAN_USER_MAX_ACTIVE": "5",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402

from app.api import auth as auth_api  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, set_engine  # noqa: E402
from app.scanner import url_safety  # noqa: E402

SITE_DIR = Path(__file__).parent / "fixtures_site"
PUBLIC_TEST_IP = "93.184.215.14"
FAKE_DNS: dict[str, list[str]] = {
    "internal.example.com": ["10.0.0.5"],
    "metadata.example.com": ["169.254.169.254"],
    "mixed.example.com": ["93.184.215.14", "192.168.1.10"],
    "v6local.example.com": ["::1"],
    "mapped.example.com": ["::ffff:127.0.0.1"],
    "rebind.example.com": ["127.0.0.1"],
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    def resolver(host: str, port: int) -> list[str]:
        if host in FAKE_DNS:
            return FAKE_DNS[host]
        if host.endswith(".invalid"):
            raise OSError("NXDOMAIN")
        return [PUBLIC_TEST_IP]

    monkeypatch.setattr(url_safety, "resolve_host", resolver)
    return FAKE_DNS


@pytest.fixture(autouse=True)
def db_engine(tmp_path: Path) -> Iterator[Any]:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    else:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    set_engine(engine)
    auth_api.login_limiter.reset()
    auth_api.register_limiter.reset()
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def settings() -> Iterator[Any]:
    s = get_settings()
    snapshot = s.model_dump()
    yield s
    for k, v in snapshot.items():
        setattr(s, k, v)


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str | None = None, password: str = "Str0ngPassw0rd") -> dict[str, Any]:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test User"})
    assert r.status_code == 201, r.text
    tokens = r.json()
    return {
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        **tokens,
    }


@pytest.fixture
def user(client: TestClient) -> dict[str, Any]:
    return register(client)


@pytest.fixture
def other_user(client: TestClient) -> dict[str, Any]:
    return register(client)


# ----------------------------------------------------------------------------- local web servers
class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # silence test output
        pass


def _serve(handler: type) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


class InternalService:
    """Plays an internal service (e.g. a database admin UI or metadata endpoint) the scanner must never reach."""

    def __init__(self) -> None:
        hits: list[str] = []
        self.hits = hits

        class Handler(_Quiet):
            def do_GET(self) -> None:  # noqa: N802
                hits.append(self.path)
                body = b"INTERNAL-SECRET"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_POST = do_GET  # noqa: N815

        self.server, self.port = _serve(Handler)
        self.url = f"http://127.0.0.1:{self.port}"


class FixtureSite:
    def __init__(self, internal: InternalService) -> None:
        self.dynamic: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self.hits: list[str] = []
        site = self

        class Handler(_Quiet):
            def __init__(self, *a: Any, **kw: Any) -> None:
                super().__init__(*a, directory=str(SITE_DIR), **kw)

            def do_GET(self) -> None:  # noqa: N802
                site.hits.append(self.path)
                path = self.path.split("?")[0]
                if path in site.dynamic:
                    code, headers, body = site.dynamic[path]
                    self.send_response(code)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

        self.server, self.port = _serve(Handler)
        self.base = f"http://127.0.0.1:{self.port}"
        self.host = f"127.0.0.1:{self.port}"
        html = lambda body: (200, {"Content-Type": "text/html; charset=utf-8"}, body.encode())  # noqa: E731
        self.dynamic.update(
            {
                "/redirect-internal": (302, {"Location": f"{internal.url}/admin"}, b""),
                "/redirect-ok": (302, {"Location": "/accessible.html"}, b""),
                "/redirect-file": (302, {"Location": "file:///etc/passwd"}, b""),
                "/ssrf-subresources.html": html(
                    f"""<!doctype html><html lang="en"><head><title>SSRF probe</title></head><body><main>
                    <h1>Sub-resource SSRF probe</h1>
                    <img src="{internal.url}/pixel.png" alt="probe">
                    <iframe src="{internal.url}/frame" title="probe frame"></iframe>
                    <script>
                      fetch("{internal.url}/fetch").catch(() => {{}});
                      try {{ new WebSocket("ws://127.0.0.1:{internal.port}/ws"); }} catch (e) {{}}
                      fetch("http://169.254.169.254/latest/meta-data/").catch(() => {{}});
                    </script></main></body></html>"""
                ),
                "/huge.html": html(
                    "<!doctype html><html lang='en'><head><title>Huge</title></head><body><main><h1>x</h1>"
                    + ("<p>" + "A" * 1000 + "</p>") * 4000
                    + "</main></body></html>"
                ),
                "/not-found.html": (404, {"Content-Type": "text/html"}, b"<html><body>Not found</body></html>"),
            }
        )

    def set_page(self, path: str, html_body: str) -> None:
        self.dynamic[path] = (200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode())


@pytest.fixture(scope="session")
def internal() -> Iterator[InternalService]:
    svc = InternalService()
    yield svc
    svc.server.shutdown()


@pytest.fixture(scope="session")
def site_server(internal: InternalService) -> Iterator[FixtureSite]:
    s = FixtureSite(internal)
    yield s
    s.server.shutdown()


@pytest.fixture
def site(site_server: FixtureSite, internal: InternalService, settings: Any) -> FixtureSite:
    """Allow-list only the fixture site (dev/test-only setting) - the internal service stays blocked."""
    settings.scanner_allow_hosts = site_server.host
    internal.hits.clear()
    site_server.hits.clear()
    return site_server
