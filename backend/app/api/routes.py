from fastapi import APIRouter, Depends, Request

from app.models.schemas import ScrapeFailure, ScrapeRequest, ScrapeSuccess
from app.services.scraper import ScrapingService

router = APIRouter(prefix="/api")


def get_scraping_service(request: Request) -> ScrapingService:
    return request.app.state.scraping_service


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "scrapted"}


@router.post("/scrape", response_model=ScrapeSuccess | ScrapeFailure)
async def scrape(
    payload: ScrapeRequest,
    service: ScrapingService = Depends(get_scraping_service),
) -> ScrapeSuccess | ScrapeFailure:
    return await service.scrape(payload)

