import ipaddress
import socket
from urllib.parse import urlsplit

import anyio

from app.core.errors import AppError

INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")


def _unsafe_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
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


def _validate_hostname(hostname: str) -> None:
    normalized = hostname.rstrip(".").lower()
    if not normalized or "." not in normalized or normalized == "localhost":
        raise AppError("URL_BLOCKED", "This URL points to a blocked destination.", 403)
    if normalized.endswith(INTERNAL_SUFFIXES):
        raise AppError("URL_BLOCKED", "This URL points to a blocked destination.", 403)
    try:
        if _unsafe_address(normalized):
            raise AppError("URL_BLOCKED", "This URL points to a blocked destination.", 403)
    except ValueError:
        return


async def validate_target_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise AppError("INVALID_URL", "Enter a public HTTP or HTTPS URL.", 400)

    hostname = parts.hostname
    _validate_hostname(hostname)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        results = await anyio.to_thread.run_sync(
            lambda: socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        )
    except socket.gaierror as error:
        raise AppError("FETCH_FAILED", "We could not resolve that website.", 502) from error

    addresses = {result[4][0] for result in results}
    if not addresses or any(_unsafe_address(address) for address in addresses):
        raise AppError("URL_BLOCKED", "This URL points to a blocked destination.", 403)

