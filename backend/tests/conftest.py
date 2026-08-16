import pytest

from app.core.config import Settings
from app.services.scraper import FetchResult
from scrapling.parser import Selector


@pytest.fixture
def settings() -> Settings:
    return Settings(gemini_api_key="test-key", max_dom_chars=24_000)


def page_result(html: str, status: int = 200, content_type: str = "text/html") -> FetchResult:
    return FetchResult(
        page=Selector(content=html, url="https://example.com/products"),
        status=status,
        headers={"content-type": content_type},
        body=html.encode(),
    )

