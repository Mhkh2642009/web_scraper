from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1):\d+$"
    scrape_timeout_seconds: float = 10
    # 0 disables the raw-page cap. AI input remains bounded by max_dom_chars.
    max_response_bytes: int = 0
    max_dom_chars: int = 12_000
    ai_confidence_threshold: float = 0.65
    dynamic_fallback_enabled: bool = True
    dynamic_fallback_min_text_chars: int = 300
    dynamic_timeout_milliseconds: int = 30_000

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
