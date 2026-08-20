import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import anyio
from scrapling.fetchers import DynamicFetcher, Fetcher
from scrapling.parser import Selector

from app.core.config import Settings
from app.core.errors import AppError, InvalidSelectorError
from app.core.security import validate_target_url
from app.models.schemas import Method, ScrapeFailure, ScrapeRequest, ScrapeSuccess, TraceEntry
from app.services.ai import AIService
from app.services.extraction import (
    build_prompt_candidates,
    build_source_preview,
    element_html,
    extract_value,
    generate_candidates,
    select_verified_element,
)


@dataclass
class FetchResult:
    page: Selector
    status: int
    headers: dict[str, str]
    body: bytes


ProgressCallback = Callable[[dict[str, str]], Awaitable[None]]


class ScraplingFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self, url: str) -> FetchResult:
        try:
            response = Fetcher.get(
                url,
                timeout=self.settings.scrape_timeout_seconds,
                retries=1,
                follow_redirects="safe",
                max_redirects=5,
                verify=True,
            )
        except Exception as error:
            message = str(error).lower()
            if "timeout" in message:
                raise AppError("FETCH_TIMEOUT", "The website took too long to respond.", 408) from error
            raise AppError("FETCH_FAILED", "We could not fetch that website.", 502) from error
        return FetchResult(
            page=response,
            status=int(getattr(response, "status", 0)),
            headers={str(key).lower(): str(value) for key, value in dict(getattr(response, "headers", {}) or {}).items()},
            body=bytes(getattr(response, "body", b"") or b""),
        )

    def fetch_dynamic(self, url: str) -> FetchResult:
        try:
            response = DynamicFetcher.fetch(
                url,
                headless=True,
                disable_resources=True,
                network_idle=True,
                timeout=self.settings.dynamic_timeout_milliseconds,
                retries=1,
            )
        except Exception as error:
            message = str(error).lower()
            if "timeout" in message:
                raise AppError("FETCH_TIMEOUT", "The rendered page took too long to respond.", 408) from error
            raise AppError("DYNAMIC_UNAVAILABLE", "This page needs browser rendering, which is unavailable on this server.", 503) from error
        return FetchResult(
            page=response,
            status=int(getattr(response, "status", 0)),
            headers={str(key).lower(): str(value) for key, value in dict(getattr(response, "headers", {}) or {}).items()},
            body=bytes(getattr(response, "body", b"") or b""),
        )


class ScrapingService:
    def __init__(
        self,
        settings: Settings,
        ai_service: AIService,
        fetcher: ScraplingFetcher | Callable[[str], FetchResult] | None = None,
        dynamic_fetcher: Callable[[str], FetchResult] | None = None,
    ):
        self.settings = settings
        self.ai_service = ai_service
        self.fetcher = fetcher or ScraplingFetcher(settings)
        self.dynamic_fetcher = dynamic_fetcher

    async def scrape(
        self,
        request: ScrapeRequest,
        on_progress: ProgressCallback | None = None,
        api_key: str | None = None,
    ) -> ScrapeSuccess | ScrapeFailure:
        trace: list[TraceEntry] = []
        await validate_target_url(request.url)
        trace.append(TraceEntry(stage="url_validation", message="Validated public URL."))

        result = await anyio.to_thread.run_sync(lambda: self._fetch(request.url))
        self._validate_response(result)
        trace.append(TraceEntry(stage="fetch", message="Fetched HTML with Scrapling."))
        trace.append(TraceEntry(stage="parse", message="Parsed the page DOM."))

        # Always preserve the cheap static-selector fast path. Browser rendering
        # is only needed when that path cannot answer the request.
        if request.expected_selector:
            element = self._select_direct(result.page, request.expected_selector)
            trace.append(TraceEntry(stage="direct_selector", message=f"Checked {request.expected_selector}."))
            if element is not None:
                value = extract_value(element)
                if value:
                    trace.append(TraceEntry(stage="direct_selector", message="Selector returned a meaningful element."))
                    return ScrapeSuccess(
                        value=value,
                        expected_selector=request.expected_selector,
                        detected_selector=request.expected_selector,
                        matched_html=element_html(element),
                        confidence=1.0,
                        method=Method.DIRECT_SELECTOR,
                        explanation="The expected selector matched a meaningful element, so AI recovery was not needed.",
                        trace=trace,
                        source_preview=build_source_preview(result.page, self.settings.max_dom_chars),
                        compressed_dom=element_html(element),
                    )
                trace.append(TraceEntry(stage="direct_selector", status="empty", message="Selector matched an empty element."))
            else:
                trace.append(TraceEntry(stage="direct_selector", status="missing", message="Selector returned no elements."))

        if self._can_render_dynamically() and self._needs_dynamic_render(result.page):
            trace.append(TraceEntry(stage="dynamic_render", message="Static HTML was sparse, so Scrapted rendered the page."))
            result = await anyio.to_thread.run_sync(lambda: self._fetch_dynamic(request.url))
            self._validate_response(result)
            trace.append(TraceEntry(stage="parse", message="Parsed the rendered DOM."))
            if request.expected_selector:
                element = self._select_direct(result.page, request.expected_selector)
                trace.append(TraceEntry(stage="direct_selector", message=f"Rechecked {request.expected_selector} in the rendered DOM."))
                if element is not None:
                    value = extract_value(element)
                    if value:
                        trace.append(TraceEntry(stage="direct_selector", message="Selector returned a meaningful element."))
                        return ScrapeSuccess(
                            value=value,
                            expected_selector=request.expected_selector,
                            detected_selector=request.expected_selector,
                            matched_html=element_html(element),
                            confidence=1.0,
                            method=Method.DIRECT_SELECTOR,
                            explanation="The expected selector matched after browser rendering, so AI recovery was not needed.",
                            trace=trace,
                            source_preview=build_source_preview(result.page, self.settings.max_dom_chars),
                            compressed_dom=element_html(element),
                        )

        source_preview = build_source_preview(result.page, self.settings.max_dom_chars)
        if on_progress:
            await on_progress({"type": "source_ready", "source_preview": source_preview})
        candidates = generate_candidates(result.page, request.query, request.expected_selector)
        trace.append(TraceEntry(stage="candidate_generation", message=f"Prepared {len(candidates)} DOM candidates."))
        if not candidates:
            return self._not_found(trace, source_preview=source_preview)
        prompt_candidates = build_prompt_candidates(candidates, self.settings.max_dom_chars)
        if on_progress:
            await on_progress({
                "type": "compressed_dom",
                "compressed_dom": prompt_candidates,
            })
            await on_progress({"type": "ai_waiting", "message": "AI is inspecting the compressed DOM candidates."})
        choice = await self.ai_service.locate(
            request.query,
            request.expected_selector,
            prompt_candidates,
            api_key=api_key,
        )
        trace.append(TraceEntry(stage="ai", message="AI evaluated the candidate elements."))
        if not choice.found or choice.confidence < self.settings.ai_confidence_threshold:
            trace.append(TraceEntry(stage="verify", status="rejected", message="No AI answer met the confidence threshold."))
            return self._not_found(trace, source_preview=source_preview, compressed_dom=prompt_candidates)

        element = select_verified_element(result.page, candidates, choice)
        if element is None:
            trace.append(TraceEntry(stage="verify", status="rejected", message="The AI choice could not be verified against the page."))
            return self._not_found(trace, source_preview=source_preview, compressed_dom=prompt_candidates)
        value = extract_value(element, choice.value_source)
        if not value:
            trace.append(TraceEntry(stage="verify", status="rejected", message="The verified element had no meaningful value."))
            return self._not_found(trace, source_preview=source_preview, compressed_dom=prompt_candidates)
        try:
            detected_selector = str(element.generate_css_selector)
        except Exception:
            detected_selector = choice.selector or ""
        if not detected_selector:
            return self._not_found(trace, source_preview=source_preview, compressed_dom=prompt_candidates)
        trace.append(TraceEntry(stage="verify", message="Verified the selected element against the parsed DOM."))
        method = Method.AI_RECOVERY if request.expected_selector else Method.AI_DISCOVERY
        return ScrapeSuccess(
            value=value,
            expected_selector=request.expected_selector,
            detected_selector=detected_selector,
            matched_html=element_html(element),
            confidence=choice.confidence,
            method=method,
            explanation=choice.reason,
            trace=trace,
            source_preview=source_preview,
            compressed_dom=prompt_candidates,
        )

    def _fetch(self, url: str) -> FetchResult:
        if callable(self.fetcher):
            return self.fetcher(url)
        return self.fetcher.fetch(url)

    def _fetch_dynamic(self, url: str) -> FetchResult:
        if self.dynamic_fetcher:
            return self.dynamic_fetcher(url)
        if isinstance(self.fetcher, ScraplingFetcher):
            return self.fetcher.fetch_dynamic(url)
        raise AppError("DYNAMIC_UNAVAILABLE", "This page needs browser rendering, which is unavailable on this server.", 503)

    def _can_render_dynamically(self) -> bool:
        return self.dynamic_fetcher is not None or isinstance(self.fetcher, ScraplingFetcher)

    def _needs_dynamic_render(self, page: Selector) -> bool:
        if not self.settings.dynamic_fallback_enabled:
            return False
        try:
            text = str(page.get_all_text(separator=" ", strip=True))
            main_nodes = page.css("main")
            main_is_empty = bool(main_nodes) and not str(
                main_nodes[0].get_all_text(separator=" ", strip=True)
            )
            script_sources = " ".join(
                str(getattr(script, "attrib", {}).get("src", "")) for script in page.css("script")
            ).lower()
        except Exception:
            return False
        javascript_shell = main_is_empty and bool(re.search(r"(?:_next|react|vue|angular|svelte)", script_sources))
        return len(text) < self.settings.dynamic_fallback_min_text_chars or javascript_shell

    def _validate_response(self, result: FetchResult) -> None:
        if result.status in {401, 403, 429}:
            raise AppError("SCRAPING_BLOCKED", "The website blocked this scraping request.", 502)
        if result.status < 200 or result.status >= 300:
            raise AppError("FETCH_FAILED", "The website returned an unsuccessful response.", 502)
        if self.settings.max_response_bytes > 0 and len(result.body) > self.settings.max_response_bytes:
            raise AppError("RESPONSE_TOO_LARGE", "The website response is too large to process safely.", 502)
        content_type = result.headers.get("content-type", "").lower()
        if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
            raise AppError("UNSUPPORTED_CONTENT", "The URL did not return an HTML page.", 502)

    @staticmethod
    def _select_direct(page: Selector, selector: str) -> Selector | None:
        try:
            matches = page.css(selector)
        except Exception as error:
            raise InvalidSelectorError() from error
        return matches[0] if matches else None

    @staticmethod
    def _not_found(trace: list[TraceEntry], source_preview: str = "", compressed_dom: str = "") -> ScrapeFailure:
        return ScrapeFailure(
            code="ELEMENT_NOT_FOUND",
            error="We couldn't confidently locate that element.",
            trace=trace,
            source_preview=source_preview,
            compressed_dom=compressed_dom,
        )
