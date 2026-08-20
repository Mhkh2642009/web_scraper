from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class Method(str, Enum):
    DIRECT_SELECTOR = "direct_selector"
    AI_RECOVERY = "ai_recovery"
    AI_DISCOVERY = "ai_discovery"


class TraceEntry(BaseModel):
    stage: str
    status: str = "done"
    message: str


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    query: str = Field(min_length=3, max_length=500)
    expected_selector: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Enter a valid HTTP or HTTPS URL.")
        return value

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Describe the element in at least 3 characters.")
        return value

    @field_validator("expected_selector")
    @classmethod
    def normalize_selector(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ScrapeSuccess(BaseModel):
    success: bool = True
    value: str
    expected_selector: str | None
    detected_selector: str
    matched_html: str
    confidence: float = Field(ge=0, le=1)
    method: Method
    explanation: str
    trace: list[TraceEntry]
    source_preview: str = ""
    compressed_dom: str = ""


class ScrapeFailure(BaseModel):
    success: bool = False
    code: str
    error: str
    trace: list[TraceEntry] = Field(default_factory=list)
    source_preview: str = ""
    compressed_dom: str = ""


class AIChoice(BaseModel):
    found: bool
    candidate_index: int | None = Field(default=None, ge=0)
    selector: str | None = Field(default=None, max_length=1000)
    value: str | None = Field(default=None, max_length=10_000)
    value_source: str | None = Field(default=None, max_length=32)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=500)
