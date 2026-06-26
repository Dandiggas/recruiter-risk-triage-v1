from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


class UnsafeURL(ValueError):
    """Raised when a URL would cause unsafe local/private network access."""


Resolver = Callable[[str], Iterable[str]]


def _default_resolver(hostname: str) -> list[str]:
    records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in records})


def _host_ips(hostname: str, resolver: Resolver | None = None) -> list[ipaddress._BaseAddress]:
    try:
        literal = ipaddress.ip_address(hostname.strip("[]"))
        return [literal]
    except ValueError:
        pass
    resolve = resolver or _default_resolver
    return [ipaddress.ip_address(value) for value in resolve(hostname)]


def _is_blocked_ip(address: ipaddress._BaseAddress) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_public_http_url(url: str, resolver: Resolver | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURL("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise UnsafeURL("URL must include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise UnsafeURL("Localhost URLs are blocked")
    try:
        addresses = _host_ips(host, resolver=resolver)
    except Exception as exc:  # DNS failures should fail closed for live fetches.
        raise UnsafeURL(f"Could not resolve URL host safely: {exc}") from exc
    if not addresses:
        raise UnsafeURL("URL host resolved to no addresses")
    blocked = [str(address) for address in addresses if _is_blocked_ip(address)]
    if blocked:
        raise UnsafeURL(f"URL resolves to blocked address range: {', '.join(blocked[:3])}")


class SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, resolver: Resolver | None = None):
        self.resolver = resolver
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook signature
        validate_public_http_url(newurl, resolver=self.resolver)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(request: Request, timeout: int = 10, resolver: Resolver | None = None):
    validate_public_http_url(request.full_url, resolver=resolver)
    opener = build_opener(SafeRedirectHandler(resolver=resolver))
    return opener.open(request, timeout=timeout)
