import httpx
import pytest

from app.core.errors import AppError
from app.services.ai import GeminiAIService


def gemini_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.mark.asyncio
async def test_gemini_output_is_validated(settings):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=gemini_response('{"found":true,"candidate_index":0,"selector":"#price","value":"$29.99","value_source":"text","confidence":0.9,"reason":"Matched price."}')))
    async with httpx.AsyncClient(transport=transport) as client:
        choice = await GeminiAIService(settings, client).locate("find price", None, "[0] span | css:#price | text:$29.99")
    assert choice.candidate_index == 0
    assert choice.confidence == .9


@pytest.mark.asyncio
async def test_invalid_gemini_output_is_rejected(settings):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=gemini_response('{"found":"maybe"}')))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AppError) as error:
            await GeminiAIService(settings, client).locate("find price", None, "[0] span | css:#price | text:$29.99")
    assert error.value.code == "AI_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_user_api_key_is_used_for_generation(settings):
    seen_key = ""

    def respond(request):
        nonlocal seen_key
        seen_key = request.headers["x-goog-api-key"]
        return httpx.Response(200, json=gemini_response('{"found":false,"confidence":0.0,"reason":"No match."}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await GeminiAIService(settings, client).locate("find price", None, "[0] span", api_key="user-owned-key")
    assert seen_key == "user-owned-key"


@pytest.mark.asyncio
async def test_gemini_key_validation_rejects_bad_key(settings):
    transport = httpx.MockTransport(lambda _request: httpx.Response(403, json={"error": {"message": "forbidden"}}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AppError) as error:
            await GeminiAIService(settings, client).validate_key("bad-key")
    assert error.value.code == "INVALID_API_KEY"
