"""Authentication, token security and account management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.security import JWT_AUDIENCE, JWT_ISSUER
from tests.conftest import register


def test_register_login_me(client: TestClient) -> None:
    u = register(client, "Alice@Example.com")
    me = client.get("/api/v1/users/me", headers=u["headers"]).json()
    assert me["email"] == "alice@example.com" and "password_hash" not in me
    r = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": u["password"]})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_duplicate_and_weak_passwords(client: TestClient) -> None:
    register(client, "bob@example.com")
    r = client.post("/api/v1/auth/register", json={"email": "bob@example.com", "password": "Str0ngPassw0rd"})
    assert r.status_code == 409
    for weak in ("short1A", "alllowercase123", "NoDigitsHereAtAll", "ALLUPPER12345"):
        r = client.post("/api/v1/auth/register", json={"email": "c@example.com", "password": weak})
        assert r.status_code == 422, weak
    assert (
        client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "Str0ngPassw0rd"}).status_code
        == 422
    )


def test_password_is_hashed_with_argon2(client: TestClient, db_engine) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    register(client, "hash@example.com", "Str0ngPassw0rd")
    with db_engine.connect() as c:
        h = c.execute(text("select password_hash from users where email='hash@example.com'")).scalar()
    assert h.startswith("$argon2id$") and "Str0ngPassw0rd" not in h


def test_wrong_password_and_unknown_user_same_error(client: TestClient) -> None:
    register(client, "carol@example.com")
    a = client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "Wr0ngPassword"})
    b = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Wr0ngPassword"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_rate_limit(client: TestClient) -> None:
    register(client, "dave@example.com")
    codes = [
        client.post("/api/v1/auth/login", json={"email": "dave@example.com", "password": "Wr0ngPass1"}).status_code
        for _ in range(12)
    ]
    assert codes[-1] == 429 and 401 in codes


def test_protected_routes_require_auth(client: TestClient) -> None:
    for path in (
        "/api/v1/users/me",
        "/api/v1/websites",
        "/api/v1/scans",
        "/api/v1/issues",
        "/api/v1/dashboard",
        "/api/v1/reports",
        "/api/v1/analytics",
        "/api/v1/monitoring",
        "/api/v1/notifications",
    ):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def _forge(sub: str, **overrides) -> str:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "ver": 0,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        **overrides,
    }
    return jwt.encode(payload, "test-secret-key-that-is-long-enough-0123456789", algorithm="HS256")


def test_jwt_tampering_rejected(client: TestClient, user) -> None:  # type: ignore[no-untyped-def]
    me = client.get("/api/v1/users/me", headers=user["headers"]).json()
    ok = _forge(me["id"])
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {ok}"}).status_code == 200
    bad_tokens = [
        jwt.encode(
            {
                "sub": me["id"],
                "type": "access",
                "aud": JWT_AUDIENCE,
                "iss": JWT_ISSUER,
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iat": datetime.now(UTC),
            },
            "a-different-secret-key-that-is-long-enough",
            algorithm="HS256",
        ),
        _forge(me["id"], exp=datetime.now(UTC) - timedelta(seconds=5)),  # expired
        _forge(me["id"], aud="other-service"),
        _forge(me["id"], type="refresh"),
        _forge(me["id"], ver=7),  # revoked token version
        _forge("00000000-0000-0000-0000-000000000000"),
        jwt.encode({"sub": me["id"], "type": "access"}, key="", algorithm="none")
        if "none" in jwt.algorithms.get_default_algorithms()
        else "x.y.z",
    ]
    for t in bad_tokens:
        assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client: TestClient, user) -> None:  # type: ignore[no-untyped-def]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]
    # replaying the old (rotated) token is detected and revokes the whole family
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, user) -> None:  # type: ignore[no-untyped-def]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": user["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh_token"]}).status_code == 401


def test_password_change_invalidates_sessions(client: TestClient, user) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/users/me/password",
        headers=user["headers"],
        json={"current_password": "wrong", "new_password": "N3wPassword99"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/v1/users/me/password",
        headers=user["headers"],
        json={"current_password": user["password"], "new_password": "N3wPassword99"},
    )
    assert r.status_code == 204
    assert client.get("/api/v1/users/me", headers=user["headers"]).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh_token"]}).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json={"email": user["email"], "password": "N3wPassword99"}).status_code == 200
    )


def test_profile_update_and_account_deletion(client: TestClient, user) -> None:  # type: ignore[no-untyped-def]
    r = client.patch(
        "/api/v1/users/me", headers=user["headers"], json={"full_name": "  Renamed  ", "notify_regressions": False}
    )
    assert r.json()["full_name"] == "Renamed" and r.json()["notify_regressions"] is False
    client.post("/api/v1/websites", headers=user["headers"], json={"name": "Site", "url": "https://example.com"})
    assert (
        client.request("DELETE", "/api/v1/users/me", headers=user["headers"], json={"password": "nope"}).status_code
        == 400
    )
    assert (
        client.request(
            "DELETE", "/api/v1/users/me", headers=user["headers"], json={"password": user["password"]}
        ).status_code
        == 204
    )
    assert (
        client.post("/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}).status_code
        == 401
    )


def test_security_headers_and_health(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/health/live").json() == {"status": "ok"}


def test_cors_only_configured_origins(client: TestClient) -> None:
    ok = client.options(
        "/api/v1/auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(
        "/api/v1/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_body_rejected(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", content=b"x" * 1_100_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_public_meta(client: TestClient) -> None:
    r = client.get("/api/v1/meta").json()
    assert r["ephemeral_demo"] is False and r["registration_enabled"] is True and "version" in r
