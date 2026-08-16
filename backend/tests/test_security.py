import socket

import pytest

from app.core.errors import AppError
from app.core.security import validate_target_url


@pytest.mark.asyncio
async def test_public_url_is_allowed(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    await validate_target_url("https://example.com/products")


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://localhost:8000", "https://service.internal"])
async def test_internal_hosts_are_blocked(url):
    with pytest.raises(AppError) as error:
        await validate_target_url(url)
    assert error.value.code == "URL_BLOCKED"


@pytest.mark.asyncio
async def test_private_dns_answer_is_blocked(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443))],
    )
    with pytest.raises(AppError) as error:
        await validate_target_url("https://example.com")
    assert error.value.code == "URL_BLOCKED"

