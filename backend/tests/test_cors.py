import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_local_vite_port_passes_cors_preflight():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/scrape",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5175"
