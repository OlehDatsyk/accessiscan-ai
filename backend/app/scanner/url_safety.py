"""URL validation and SSRF protection.

Layer 1 of the scanner's network defence (see SECURITY.md). Every user-supplied URL is validated here
before it is stored or navigated to:

* only ``http``/``https``; no credentials in URLs; bounded length; no control characters;
* only allowed ports;
* hostnames such as ``localhost``, ``*.local`` and ``*.internal`` are refused outright;
* the host is resolved and EVERY resulting address must be a public, globally routable unicast address
  (loopback, RFC 1918, link-local incl. 169.254.169.254 metadata, CGNAT, ULA, multicast, reserved,
  IPv4-mapped/NAT64/6to4/Teredo forms of those, etc. are refused).

Layer 2 is the guarded proxy (``proxy.py``), which repeats the IP checks for every single browser
connection (including redirects, sub-resources and WebSockets) and pins the connection to the validated
IP, which defeats DNS rebinding between check and use.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.config import get_settings

MAX_URL_LENGTH = 2048
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home.arpa",
    ".corp",
    ".private",
)
_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "kubernetes",
    "kubernetes.default",
}
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_EXTRA_BLOCKED_V4 = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "100.64.0.0/10",  # CGNAT (also Alibaba metadata 100.100.100.200)
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
]


class UnsafeURLError(ValueError):
    """Raised when a URL is not permitted as a scan target."""


@dataclass(frozen=True)
class SafeURL:
    url: str  # normalised, fragment removed
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]


def is_public_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        ip = ipaddress.ip_address(value) if isinstance(value, str) else value
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(ip.ipv4_mapped)
        if ip in _NAT64:
            return is_public_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if ip.sixtofour is not None:
            return is_public_ip(ip.sixtofour)
        if ip.teredo is not None:
            return False
        if ip.scope_id:
            return False
    else:
        if any(ip in net for net in _EXTRA_BLOCKED_V4):
            return False
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def resolve_host(host: str, port: int) -> list[str]:
    """Resolve a hostname to all of its addresses. Replaced in tests to simulate DNS answers."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]).split("%")[0] for info in infos})


def _host_allowlisted(host: str, port: int) -> bool:
    settings = get_settings()
    if settings.environment == "production":
        return False
    return f"{host}:{port}" in settings.allow_hosts


def check_host_name(host: str) -> None:
    if not host:
        raise UnsafeURLError("The URL has no host name")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise UnsafeURLError("Local and internal host names cannot be scanned")
    if len(host) > 253:
        raise UnsafeURLError("The host name is too long")


def _parse_ipv4_number(part: str) -> int | None:
    if part == "":
        return None
    try:
        if part.startswith(("0x", "0X")):
            return int(part[2:] or "0", 16)
        if len(part) > 1 and part.startswith("0"):
            return int(part[1:], 8)
        return int(part, 10)
    except ValueError:
        return None


def legacy_ipv4(host: str) -> str | None:
    """WHATWG URL IPv4 parsing: browsers treat '127.1', '2130706433', '0x7f.1' or '0177.0.0.1' as IPv4.

    Returns the dotted-quad form, or None if the host is not a (legacy) numeric IPv4 host.
    Raises UnsafeURLError for hosts that look numeric but are invalid.
    """
    labels = host.split(".")
    if not labels or _parse_ipv4_number(labels[-1]) is None:
        return None
    if len(labels) > 4:
        raise UnsafeURLError("The host name is not valid")
    nums = [_parse_ipv4_number(p) for p in labels]
    if any(n is None for n in nums):
        raise UnsafeURLError("The host name is not valid")
    values = [int(n) for n in nums if n is not None]
    if any(v > 255 for v in values[:-1]) or values[-1] >= 256 ** (5 - len(values)):
        raise UnsafeURLError("The host name is not valid")
    ipv4 = values[-1]
    for i, v in enumerate(values[:-1]):
        ipv4 += v * 256 ** (3 - i)
    return str(ipaddress.IPv4Address(ipv4))


def normalise_host(raw_host: str) -> str:
    host = raw_host.strip().rstrip(".").lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    legacy = legacy_ipv4(host)
    if legacy is not None:
        return legacy
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeURLError("The host name is not valid") from exc


def parse_and_normalise(raw: str) -> tuple[str, str, str, int]:
    """Syntactic validation only. Returns (normalised_url, scheme, host, port)."""
    if not isinstance(raw, str):
        raise UnsafeURLError("URL must be text")
    url = raw.strip()
    if not url:
        raise UnsafeURLError("Enter a URL")
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeURLError(f"URLs longer than {MAX_URL_LENGTH} characters are not supported")
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in url) or "\\" in url:
        raise UnsafeURLError("The URL contains characters that are not allowed")
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("The URL is not valid") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs can be scanned")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeURLError("URLs containing credentials are not allowed")
    if parts.hostname is None:
        raise UnsafeURLError("The URL has no host name")
    host = normalise_host(parts.hostname)
    check_host_name(host)
    effective_port = port or (443 if scheme == "https" else 80)
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    normalised = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
    return normalised, scheme, host, effective_port


def check_port(host: str, port: int) -> None:
    if port not in get_settings().allowed_ports and not _host_allowlisted(host, port):
        raise UnsafeURLError(f"Port {port} is not permitted for scanning")


def check_addresses(host: str, port: int, addresses: list[str]) -> None:
    if _host_allowlisted(host, port):
        return
    if not addresses:
        raise UnsafeURLError("The host name did not resolve to any address")
    for addr in addresses:
        if not is_public_ip(addr):
            raise UnsafeURLError("The URL resolves to a private, local or reserved network address")


def validate_target(raw: str, *, resolve: bool = True) -> SafeURL:
    """Full validation of a scan target. Raises UnsafeURLError with a user-safe message."""
    url, scheme, host, port = parse_and_normalise(raw)
    check_port(host, port)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        check_addresses(host, port, [str(literal)])
        return SafeURL(url, scheme, host, port, (str(literal),))
    if not resolve:
        return SafeURL(url, scheme, host, port, ())
    try:
        addresses = resolve_host(host, port)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise UnsafeURLError("The host name could not be resolved") from exc
    check_addresses(host, port, addresses)
    return SafeURL(url, scheme, host, port, tuple(addresses))


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.scheme, pa.hostname, pa.port or (443 if pa.scheme == "https" else 80)) == (
        pb.scheme,
        pb.hostname,
        pb.port or (443 if pb.scheme == "https" else 80),
    )
