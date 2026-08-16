import pytest

from app.core.errors import AppError
from app.models.schemas import AIChoice, Method, ScrapeRequest
from app.services.scraper import ScrapingService
from tests.conftest import page_result


class FakeAI:
    def __init__(self, choice: AIChoice):
        self.choice = choice
        self.calls = 0

    async def locate(self, *_args, **_kwargs) -> AIChoice:
        self.calls += 1
        return self.choice


async def allow_url(_url: str) -> None:
    return None


@pytest.mark.asyncio
async def test_direct_selector_skips_ai(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    service = ScrapingService(settings, ai, lambda _url: page_result("<html><body><span id='price'>$29.99</span></body></html>"))
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find price", expected_selector="#price"))
    assert result.success is True
    assert result.method == Method.DIRECT_SELECTOR
    assert result.value == "$29.99"
    assert ai.calls == 0


@pytest.mark.asyncio
async def test_broken_selector_uses_verified_candidate(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    ai = FakeAI(AIChoice(found=True, candidate_index=0, selector="#new-price", value="$29.99", value_source="text", confidence=.94, reason="The price candidate matches the query."))
    service = ScrapingService(settings, ai, lambda _url: page_result("<html><body><span id='new-price'>$29.99</span></body></html>"))
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find price", expected_selector="#old-price"))
    assert result.success is True
    assert result.method == Method.AI_RECOVERY
    assert result.detected_selector == "#new-price"
    assert ai.calls == 1


@pytest.mark.asyncio
async def test_low_confidence_returns_not_found(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    ai = FakeAI(AIChoice(found=True, candidate_index=0, selector="#price", value="$29.99", value_source="text", confidence=.2, reason="uncertain"))
    service = ScrapingService(settings, ai, lambda _url: page_result("<html><body><span id='price'>$29.99</span></body></html>"))
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find price"))
    assert result.success is False
    assert result.code == "ELEMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_direct_selector_is_a_client_error(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    service = ScrapingService(settings, ai, lambda _url: page_result("<html><body><span id='price'>$29.99</span></body></html>"))
    with pytest.raises(AppError) as error:
        await service.scrape(ScrapeRequest(url="https://example.com", query="find price", expected_selector="["))
    assert error.value.code == "INVALID_SELECTOR"

