import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from scrapling.parser import Selector

from app.models.schemas import AIChoice

SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link", "template", "head"}
USEFUL_ATTRIBUTES = ("id", "class", "href", "src", "aria-label", "name", "title", "alt", "value", "content", "data-testid")
VALUE_ATTRIBUTES = ("value", "content", "aria-label", "alt", "title", "href", "src")
TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)
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

    def to_prompt(self) -> dict[str, Any]:
        return {
            "candidate_index": self.index,
            "selector": self.selector,
            "tag": self.tag,
            "attributes": self.attributes,
            "text": self.text,
            "parent_context": self.parent_context,
        }


def compact(value: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def element_attributes(element: Selector) -> dict[str, str]:
    attributes = getattr(element, "attrib", {}) or {}
    return {key: compact(value, 180) for key, value in attributes.items() if key in USEFUL_ATTRIBUTES and value}


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


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(value)}


def _score_candidate(candidate: Candidate, query: str, expected_selector: str | None) -> float:
    query_tokens = _tokens(query)
    candidate_text = " ".join([candidate.tag, candidate.selector, candidate.text, *candidate.attributes.values()]).lower()
    candidate_tokens = _tokens(candidate_text)
    overlap = len(query_tokens & candidate_tokens) * 4
    score = overlap + min(len(candidate.text), 180) / 180
    if expected_selector:
        expected_tokens = _tokens(expected_selector)
        score += len(expected_tokens & candidate_tokens) * 5
        score += SequenceMatcher(None, expected_selector.lower(), candidate.selector.lower()).ratio() * 3
    if candidate.attributes.get("id") or candidate.attributes.get("data-testid"):
        score += 1.5
    if candidate.tag in {"h1", "h2", "h3", "p", "span", "a", "button", "input", "time"}:
        score += 0.5
    return score


def _parent_context(element: Selector) -> str:
    try:
        parent = getattr(element, "parent", None)
        if parent is None:
            return ""
        return compact(f"{parent.tag} {element_text(parent)}", 280)
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


def build_prompt_candidates(candidates: list[Candidate], max_chars: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    used = 0
    for candidate in candidates:
        payload = candidate.to_prompt()
        serialized = str(payload)
        if used + len(serialized) > max_chars:
            break
        result.append(payload)
        used += len(serialized)
    return result


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

