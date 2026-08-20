import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from scrapling.parser import Selector

from app.models.schemas import AIChoice

SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "g", "circle", "rect", "meta", "link", "template", "head"}
USEFUL_ATTRIBUTES = ("id", "class", "href", "src", "aria-label", "name", "title", "alt", "value", "content", "data-testid", "style")
VALUE_ATTRIBUTES = ("value", "content", "aria-label", "alt", "title", "href", "src")
TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)
MONEY_PATTERN = re.compile(
    r"(?:\$|€|£|EGP|USD|AED|SAR|JPY|CAD|AUD)\s*[\d,.]+|[\d,.]+\s*(?:ج\.?\s*م\.?|EGP|USD|AED|SAR|JPY|CAD|AUD)",
    re.IGNORECASE,
)
MAX_VALUE_CHARS = 10_000


@dataclass
class Candidate:
    index: int
    selector: str
    tag: str
    attributes: dict[str, str]
    text: str
    parent_context: str
    score: float
    element: Selector

    def to_prompt_line(self) -> str:
        """A compact DOM sketch for the LLM, not raw HTML."""
        identity = self.attributes.get("id", "")
        classes = " ".join(self.attributes.get("class", "").split()[:3])
        locator = self.selector
        details = []
        if identity:
            details.append(f"id={identity}")
        if classes:
            details.append(f"class={classes}")
        for key in ("data-testid", "name", "aria-label", "alt", "title", "href", "src", "value", "content"):
            value = self.attributes.get(key)
            if value:
                details.append(f"{key}={compact(value, 90)}")
        summary = f"[{self.index}] {self.tag} | css:{locator}"
        if details:
            summary += f" | {'; '.join(details)}"
        if self.text:
            summary += f" | text:{compact(self.text, 220)}"
        if self.parent_context:
            summary += f" | in:{compact(self.parent_context, 100)}"
        return summary


def compact(value: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def element_attributes(element: Selector) -> dict[str, str]:
    attributes = getattr(element, "attrib", {}) or {}
    return {
        key: compact(value, 180)
        for key, value in attributes.items()
        if (key in USEFUL_ATTRIBUTES or key.startswith("data-")) and value
    }


def element_text(element: Selector) -> str:
    try:
        return compact(str(element.get_all_text(separator=" ", strip=True)), MAX_VALUE_CHARS)
    except Exception:
        return ""


def extract_value(element: Selector, source: str | None = None) -> str:
    attributes = getattr(element, "attrib", {}) or {}
    if source and source != "text" and attributes.get(source):
        return compact(str(attributes[source]), MAX_VALUE_CHARS)
    text = element_text(element)
    if text:
        return text
    for attribute in VALUE_ATTRIBUTES:
        if attributes.get(attribute):
            return compact(str(attributes[attribute]), MAX_VALUE_CHARS)
    return ""


def element_html(element: Selector) -> str:
    return compact(str(element.get()), MAX_VALUE_CHARS)


def build_source_preview(page: Selector, max_chars: int) -> str:
    """Return a bounded, safe-to-display source view without executable page content."""
    try:
        html = str(page.get())
    except Exception:
        return ""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"<(?:script|style|noscript|svg|template)\b[^>]*>.*?</(?:script|style|noscript|svg|template)>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<(?:meta|link)\b[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r">\s*<", ">\n<", html.strip())

    lines: list[str] = []
    used = 0
    for raw_line in html.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        line = line[:800]
        if used + len(line) + 1 > max_chars:
            remaining = max_chars - used
            if remaining > 1:
                lines.append(f"{line[:remaining - 1]}…")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(value)}


def _score_candidate(candidate: Candidate, query: str, expected_selector: str | None) -> float:
    query_tokens = _tokens(query)
    candidate_text = " ".join(
        [candidate.tag, candidate.selector, candidate.text, candidate.parent_context, *candidate.attributes.values()]
    ).lower()
    candidate_tokens = _tokens(candidate_text)
    overlap = len(query_tokens & candidate_tokens) * 4
    score = overlap + (1 if candidate.text else 0)
    if expected_selector:
        expected_tokens = _tokens(expected_selector)
        score += len(expected_tokens & candidate_tokens) * 5
        score += SequenceMatcher(None, expected_selector.lower(), candidate.selector.lower()).ratio() * 3
    if candidate.attributes.get("id") or candidate.attributes.get("data-testid"):
        score += 1.5
    if candidate.tag in {"h1", "h2", "h3", "p", "span", "a", "button", "input", "time"}:
        score += 0.5
    price_intent = bool(query_tokens & {"price", "cost", "amount", "sale", "deal", "currency", "fee"})
    if price_intent:
        if MONEY_PATTERN.search(candidate.text):
            score += 16
        if MONEY_PATTERN.fullmatch(candidate.text.strip()):
            # A single currency value is far more likely to be the displayed price
            # than a container that merely discusses pricing, shipping, or reviews.
            score += 18
        if re.search(r"price|cost|amount|deal", candidate_text):
            score += 6
        if re.search(r"coreprice|apex|pricetopay|price_to_pay", candidate_text):
            score += 9
        if re.search(r"list price|a-text-price|was price|msrp", candidate_text):
            score -= 12
        if candidate.tag in {"span", "strong", "b", "ins"}:
            score += 1
        if not (query_tokens & {"review", "reviews", "feedback", "rating"}) and re.search(
            r"feedback|review|popover|recommendation", candidate.selector.lower()
        ):
            score -= 14
        if not (query_tokens & {"shipping", "delivery", "import", "fee"}) and re.search(
            r"shipping|delivery|import charges|fee details", candidate.text.lower()
        ):
            score -= 12
    if len(candidate.text) > 240:
        score -= min(8, (len(candidate.text) - 240) / 80)
    return score


def _parent_context(element: Selector) -> str:
    try:
        parent = getattr(element, "parent", None)
        if parent is None:
            return ""
        attributes = getattr(parent, "attrib", {}) or {}
        identity = " ".join(
            compact(str(attributes.get(key, "")), 80)
            for key in ("id", "class", "data-testid")
            if attributes.get(key)
        )
        return compact(f"{parent.tag} {identity} {element_text(parent)}", 280)
    except Exception:
        return ""


def generate_candidates(page: Selector, query: str, expected_selector: str | None, max_candidates: int = 40) -> list[Candidate]:
    try:
        elements = page.css("body *") or page.css("*")
    except Exception:
        return []
    candidates: list[Candidate] = []
    for element in elements:
        tag = str(getattr(element, "tag", "")).lower()
        if not tag or tag in SKIP_TAGS:
            continue
        attributes = element_attributes(element)
        if attributes.get("aria-hidden") == "true" or "display:none" in attributes.get("style", "").replace(" ", "").lower():
            continue
        text = element_text(element)
        if not text and not any(attributes.get(key) for key in VALUE_ATTRIBUTES):
            continue
        try:
            selector = str(element.generate_css_selector)
        except Exception:
            continue
        candidate = Candidate(
            index=len(candidates),
            selector=selector,
            tag=tag,
            attributes=attributes,
            text=compact(text, 500),
            parent_context=_parent_context(element),
            score=0,
            element=element,
        )
        candidate.score = _score_candidate(candidate, query, expected_selector)
        candidates.append(candidate)
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:max_candidates]
    for index, candidate in enumerate(ranked):
        candidate.index = index
    return ranked


def build_prompt_candidates(candidates: list[Candidate], max_chars: int) -> str:
    """Create a bounded, line-oriented DOM sketch without raw page HTML."""
    lines: list[str] = []
    used = 0
    for candidate in candidates:
        line = candidate.to_prompt_line()
        line_size = len(line) + 1
        if used + line_size > max_chars:
            break
        lines.append(line)
        used += line_size
    return "\n".join(lines)


def select_verified_element(page: Selector, candidates: list[Candidate], choice: AIChoice) -> Selector | None:
    if not choice.found or choice.candidate_index is None:
        return None
    candidate_by_index = {candidate.index: candidate for candidate in candidates}
    candidate = candidate_by_index.get(choice.candidate_index)
    if candidate is None:
        return None
    if choice.selector:
        try:
            matches = page.css(choice.selector)
        except Exception:
            matches = []
        if matches:
            resolved = matches[0]
            try:
                if str(resolved.generate_css_selector) == candidate.selector:
                    return resolved
            except Exception:
                pass
    return candidate.element
