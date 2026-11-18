"""Guarded egress proxy for the scanning browser (network-level SSRF defence).

Chromium is launched with ``--proxy-server`` pointing here, with the implicit loopback bypass removed
and with its own DNS resolution disabled (``--host-resolver-rules``), so EVERY browser connection —
navigations, redirects, sub-resources, fetch/XHR, WebSockets — must pass through this proxy.

For each connection the proxy:

1. checks the port against the allow-list;
2. resolves the host itself and refuses the connection unless ALL addresses are public;
3. connects to the validated IP address (pinning it, so a DNS rebinding answer that changes between
   validation and connection cannot redirect the browser to an internal address);
4. enforces per-page and per-scan byte budgets and idle timeouts.

Only ``CONNECT`` (HTTPS / WSS tunnels) and absolute-form plain-HTTP requests are supported.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import socket
from dataclasses import dataclass, field

from app.scanner import url_safety

log = logging.getLogger("accessiscan.proxy")

MAX_HEADER_BYTES = 32 * 1024
CONNECT_TIMEOUT = 10.0
IDLE_TIMEOUT = 30.0
BUF = 64 * 1024


@dataclass
class ProxyStats:
    allowed_connections: int = 0
    blocked: list[dict[str, str]] = field(default_factory=list)
    bytes_total: int = 0
    budget_exceeded: bool = False

    def record_block(self, host: str, reason: str) -> None:
        if len(self.blocked) < 200:
            self.blocked.append({"host": host[:255], "reason": reason})


class GuardedProxy:
    def __init__(self, *, max_total_bytes: int, max_page_bytes: int) -> None:
        self.max_total_bytes = max_total_bytes
        self.max_page_bytes = max_page_bytes
        self.page_bytes = 0
        self.stats = ProxyStats()
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self.port = 0

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, host="127.0.0.1", port=0, limit=MAX_HEADER_BYTES)
        sock = self._server.sockets[0]
        self.port = int(sock.getsockname()[1])
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for w in list(self._writers):
            with contextlib.suppress(Exception):
                w.close()
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def reset_page_budget(self) -> None:
        self.page_bytes = 0

    # ------------------------------------------------------------------ policy
    async def _resolve_and_check(self, host: str, port: int) -> str:
        """Return the pinned IP to connect to, or raise UnsafeURLError."""
        host = url_safety.normalise_host(host)
        url_safety.check_host_name(host)
        url_safety.check_port(host, port)
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            url_safety.check_addresses(host, port, [str(literal)])
            return str(literal)
        try:
            addresses = await asyncio.to_thread(url_safety.resolve_host, host, port)
        except (socket.gaierror, OSError, UnicodeError) as exc:
            raise url_safety.UnsafeURLError("DNS resolution failed") from exc
        url_safety.check_addresses(host, port, addresses)
        if not addresses:
            raise url_safety.UnsafeURLError("No address")
        # Prefer IPv4 for reachability in container environments.
        addresses.sort(key=lambda a: ":" in a)
        return addresses[0]

    # ------------------------------------------------------------------ connection handling
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        self._writers.add(writer)
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=IDLE_TIMEOUT)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
                return
            request_line, _, rest = head.partition(b"\r\n")
            try:
                method, target, version = request_line.decode("latin-1").split(" ", 2)
            except ValueError:
                await self._reply(writer, 400, "Bad Request")
                return

            if method.upper() == "CONNECT":
                host, port = self._split_host_port(target, default_port=443)
            else:
                if not target.lower().startswith("http://"):
                    await self._reply(writer, 400, "Bad Request")
                    return
                parts = target[len("http://") :]
                authority, _, path = parts.partition("/")
                host, port = self._split_host_port(authority, default_port=80)
                target_path = "/" + path

            if self.stats.budget_exceeded:
                self.stats.record_block(host, "scan download budget exceeded")
                await self._reply(writer, 403, "Forbidden")
                return
            try:
                ip = await self._resolve_and_check(host, port)
            except url_safety.UnsafeURLError as exc:
                self.stats.record_block(host, str(exc))
                log.info("blocked connection to %s:%s (%s)", host, port, exc)
                await self._reply(writer, 403, "Forbidden")
                return

            try:
                up_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), timeout=CONNECT_TIMEOUT
                )
            except (OSError, TimeoutError):
                await self._reply(writer, 502, "Bad Gateway")
                return
            self.stats.allowed_connections += 1

            if method.upper() == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                headers = [
                    h
                    for h in rest.split(b"\r\n")
                    if h and not h.lower().startswith((b"proxy-connection:", b"proxy-authorization:", b"connection:"))
                ]
                new_head = f"{method} {target_path} {version}\r\n".encode("latin-1")
                new_head += b"\r\n".join(headers) + b"\r\nConnection: close\r\n\r\n"
                upstream_writer.write(new_head)
                await upstream_writer.drain()

            await asyncio.gather(
                self._pipe(reader, upstream_writer, count=False),
                self._pipe(up_reader, writer, count=True),
            )
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - never let a single connection crash the proxy
            log.debug("proxy connection error", exc_info=True)
        finally:
            for w in (writer, upstream_writer):
                if w is not None:
                    with contextlib.suppress(Exception):
                        w.close()
            self._writers.discard(writer)
            if task is not None:
                self._tasks.discard(task)

    async def _pipe(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter, *, count: bool) -> None:
        try:
            while True:
                data = await asyncio.wait_for(src.read(BUF), timeout=IDLE_TIMEOUT)
                if not data:
                    break
                if count:
                    self.stats.bytes_total += len(data)
                    self.page_bytes += len(data)
                    if self.stats.bytes_total > self.max_total_bytes or self.page_bytes > self.max_page_bytes:
                        self.stats.budget_exceeded = self.stats.bytes_total > self.max_total_bytes
                        self.stats.record_block("*", "download size limit reached")
                        break
                dst.write(data)
                await dst.drain()
        except (TimeoutError, ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            with contextlib.suppress(Exception):
                if dst.can_write_eof():
                    dst.write_eof()
                else:
                    dst.close()

    @staticmethod
    def _split_host_port(authority: str, *, default_port: int) -> tuple[str, int]:
        authority = authority.strip()
        if "@" in authority:
            raise url_safety.UnsafeURLError("credentials in proxy authority")
        if authority.startswith("["):
            host, _, rest = authority[1:].partition("]")
            port_s = rest[1:] if rest.startswith(":") else ""
        elif authority.count(":") == 1:
            host, _, port_s = authority.partition(":")
        else:
            host, port_s = authority, ""
        try:
            port = int(port_s) if port_s else default_port
        except ValueError:
            port = -1
        return host, port

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, code: int, reason: str) -> None:
        with contextlib.suppress(Exception):
            body = f"AccessiScan scanner policy: {reason}".encode()
            writer.write(
                f"HTTP/1.1 {code} {reason}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
