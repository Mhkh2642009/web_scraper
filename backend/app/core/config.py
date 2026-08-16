from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    cors_origins: str = "http://localhost:5173"
    scrape_timeout_seconds: float = 10
    max_response_bytes: int = 2 * 1024 * 1024
    max_dom_chars: int = 24_000
    ai_confidence_threshold: float = 0.65

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

