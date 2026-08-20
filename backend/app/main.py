from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schemas import ScrapeFailure
from app.services.ai import GeminiAIService
from app.services.scraper import ScrapingService


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Scrapted API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Gemini-API-Key"],
    )
    ai_service = GeminiAIService(settings)
    app.state.gemini_ai_service = ai_service
    app.state.scraping_service = ScrapingService(settings, ai_service)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, error: AppError) -> JSONResponse:
        failure = ScrapeFailure(code=error.code, error=error.message)
        return JSONResponse(status_code=error.status_code, content=failure.model_dump(exclude={"source_preview", "compressed_dom"}))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        failure = ScrapeFailure(code="INVALID_REQUEST", error="Check the URL, query, and selector fields.")
        return JSONResponse(status_code=422, content=failure.model_dump(exclude={"source_preview", "compressed_dom"}))

    app.include_router(router)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
