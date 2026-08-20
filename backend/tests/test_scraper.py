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


@pytest.mark.asyncio
async def test_large_page_is_accepted_when_raw_cap_is_disabled(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    settings.max_response_bytes = 0
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    html = "<html><body><h1>Large page</h1>" + ("x" * 5_000) + "</body></html>"
    service = ScrapingService(settings, ai, lambda _url: page_result(html))
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find heading", expected_selector="h1"))
    assert result.success is True
    assert result.value == "Large page"


@pytest.mark.asyncio
async def test_raw_cap_can_still_be_enabled_for_deployments(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    settings.max_response_bytes = 100
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    service = ScrapingService(settings, ai, lambda _url: page_result("<html><body><h1>Large page</h1>" + ("x" * 200) + "</body></html>"))
    with pytest.raises(AppError) as error:
        await service.scrape(ScrapeRequest(url="https://example.com", query="find heading", expected_selector="h1"))
    assert error.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_sparse_static_shell_uses_rendered_page(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    static_page = page_result("<html><body><div id='app'>Loading documentation…</div></body></html>")
    rendered_page = page_result("<html><body><main><h2 id='authentication'>Authentication overview</h2><p>Use your API token.</p></main></body></html>")
    settings.dynamic_fallback_min_text_chars = 100
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    service = ScrapingService(
        settings,
        ai,
        lambda _url: static_page,
        dynamic_fetcher=lambda _url: rendered_page,
    )
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find authentication", expected_selector="#authentication"))
    assert result.success is True
    assert result.value == "Authentication overview"
    assert any(entry.stage == "dynamic_render" for entry in result.trace)


@pytest.mark.asyncio
async def test_empty_main_in_javascript_shell_uses_rendered_page(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    static_page = page_result("<html><body><header>Book store</header><main></main><footer>Contact</footer><script src='/_next/static/app.js'></script></body></html>")
    rendered_page = page_result("<html><body><main><span id='price'>220 EGP</span></main></body></html>")
    ai = FakeAI(AIChoice(found=False, confidence=0, reason="unused"))
    service = ScrapingService(settings, ai, lambda _url: static_page, dynamic_fetcher=lambda _url: rendered_page)
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="find price", expected_selector="#price"))
    assert result.success is True
    assert result.value == "220 EGP"
    assert any(entry.stage == "dynamic_render" for entry in result.trace)


@pytest.mark.asyncio
async def test_sparse_page_without_loading_text_uses_rendered_recovery(settings, monkeypatch):
    monkeypatch.setattr("app.services.scraper.validate_target_url", allow_url)
    static_page = page_result("<html><body><title>Teacher site</title></body></html>")
    rendered_page = page_result("<html><body><main><h1 id='teacher-name'>Waleed Physics</h1></main></body></html>")
    ai = FakeAI(AIChoice(found=True, candidate_index=0, selector="#teacher-name", value="ignored", value_source="text", confidence=.9, reason="The visible heading identifies the teacher."))
    service = ScrapingService(settings, ai, lambda _url: static_page, dynamic_fetcher=lambda _url: rendered_page)
    result = await service.scrape(ScrapeRequest(url="https://example.com", query="what is the teacher name?", expected_selector=".teachname"))
    assert result.success is True
    assert result.value == "Waleed Physics"
    assert result.method == Method.AI_RECOVERY
    assert any(entry.stage == "dynamic_render" for entry in result.trace)
