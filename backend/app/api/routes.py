import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.core.errors import AppError
from app.models.schemas import ScrapeFailure, ScrapeRequest, ScrapeSuccess
from app.services.ai import GeminiAIService
from app.services.scraper import ScrapingService

router = APIRouter(prefix="/api")


def get_scraping_service(request: Request) -> ScrapingService:
    return request.app.state.scraping_service


def get_ai_service(request: Request) -> GeminiAIService:
    return request.app.state.gemini_ai_service


def require_gemini_api_key(
    api_key: Annotated[str | None, Header(alias="X-Gemini-API-Key")] = None,
) -> str:
    key = (api_key or "").strip()
    if not key:
        raise AppError("API_KEY_REQUIRED", "Connect your Gemini API key before using Scrapted.", 401)
    if len(key) > 512:
        raise AppError("INVALID_API_KEY", "The Gemini API key is not valid.", 401)
    return key


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "scrapted"}


@router.post("/scrape", response_model=ScrapeSuccess | ScrapeFailure)
async def scrape(
    payload: ScrapeRequest,
    api_key: Annotated[str, Depends(require_gemini_api_key)],
    service: ScrapingService = Depends(get_scraping_service),
) -> ScrapeSuccess | ScrapeFailure:
    return await service.scrape(payload, api_key=api_key)


@router.post("/ai/validate")
async def validate_ai_key(
    api_key: Annotated[str, Depends(require_gemini_api_key)],
    service: GeminiAIService = Depends(get_ai_service),
) -> dict[str, bool]:
    await service.validate_key(api_key)
    return {"valid": True}


@router.post("/scrape/stream")
async def scrape_stream(
    payload: ScrapeRequest,
    api_key: Annotated[str, Depends(require_gemini_api_key)],
    service: ScrapingService = Depends(get_scraping_service),
) -> StreamingResponse:
    async def events():
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

        async def progress(event: dict[str, str]) -> None:
            await queue.put(event)

        task = asyncio.create_task(service.scrape(payload, on_progress=progress, api_key=api_key))
        yield "event: state\ndata: {\"type\": \"submitted\", \"message\": \"Request submitted to Scrapted.\"}\n\n"
        while not task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=.1)
            except asyncio.TimeoutError:
                continue
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        try:
            result = await task
            yield f"event: result\ndata: {result.model_dump_json()}\n\n"
        except AppError as error:
            failure = ScrapeFailure(code=error.code, error=error.message)
            yield f"event: result\ndata: {failure.model_dump_json(exclude={ 'source_preview', 'compressed_dom' })}\n\n"
        except Exception:
            failure = ScrapeFailure(code="REQUEST_FAILED", error="The request could not be completed.")
            yield f"event: result\ndata: {failure.model_dump_json(exclude={ 'source_preview', 'compressed_dom' })}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
