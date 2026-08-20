import httpx
import pytest

from app.main import create_app
from app.models.schemas import ScrapeFailure


class NoMatchService:
    async def scrape(self, _payload, **_kwargs):
        return ScrapeFailure(code="ELEMENT_NOT_FOUND", error="We couldn't confidently locate that element.")


class StreamingNoMatchService:
    async def scrape(self, _payload, on_progress=None, **_kwargs):
        if on_progress:
            await on_progress({"type": "source_ready", "source_preview": "<main>Visible</main>"})
            await on_progress({"type": "compressed_dom", "compressed_dom": "[0] main | text:Visible"})
            await on_progress({"type": "ai_waiting", "message": "AI is inspecting the compressed DOM candidates."})
        return ScrapeFailure(code="ELEMENT_NOT_FOUND", error="We couldn't confidently locate that element.")


class ValidKeyService:
    def __init__(self):
        self.key = ""

    async def validate_key(self, api_key):
        self.key = api_key


api_headers = {"X-Gemini-API-Key": "user-test-key"}


@pytest.mark.asyncio
async def test_api_returns_stable_no_match_shape():
    app = create_app()
    app.state.scraping_service = NoMatchService()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/scrape", json={"url": "https://example.com", "query": "find price"}, headers=api_headers)
    assert response.status_code == 200
    assert response.json()["code"] == "ELEMENT_NOT_FOUND"
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_api_returns_safe_validation_error():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/scrape", json={"url": "not a url", "query": "x"}, headers=api_headers)
    assert response.status_code == 422
    assert response.json() == {"success": False, "code": "INVALID_REQUEST", "error": "Check the URL, query, and selector fields.", "trace": []}


@pytest.mark.asyncio
async def test_stream_sends_inspector_before_final_result():
    app = create_app()
    app.state.scraping_service = StreamingNoMatchService()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/scrape/stream", json={"url": "https://example.com", "query": "find price"}, headers=api_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.index("event: source_ready") < response.text.index("event: compressed_dom") < response.text.index("event: result")


@pytest.mark.asyncio
async def test_scrape_requires_a_user_api_key():
    app = create_app()
    app.state.scraping_service = NoMatchService()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/scrape", json={"url": "https://example.com", "query": "find price"})
    assert response.status_code == 401
    assert response.json()["code"] == "API_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_api_key_validation_uses_the_header_key():
    app = create_app()
    validator = ValidKeyService()
    app.state.gemini_ai_service = validator
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/ai/validate", headers=api_headers)
    assert response.status_code == 200
    assert response.json() == {"valid": True}
    assert validator.key == "user-test-key"
