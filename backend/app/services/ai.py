from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.models.schemas import AIChoice


class AIService(Protocol):
    async def locate(
        self,
        query: str,
        expected_selector: str | None,
        candidates: str,
        api_key: str | None = None,
    ) -> AIChoice: ...


class GeminiAIService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def validate_key(self, api_key: str) -> None:
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
        try:
            if self.client:
                response = await self.client.get(url, headers={"x-goog-api-key": api_key})
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(url, headers={"x-goog-api-key": api_key})
        except httpx.TimeoutException as error:
            raise AppError("AI_UNAVAILABLE", "Gemini took too long to verify the key. Try again shortly.", 503) from error
        except httpx.HTTPError as error:
            raise AppError("AI_UNAVAILABLE", "Gemini could not verify the key. Try again shortly.", 503) from error
        self._raise_for_key_response(response)
        if response.status_code == 429:
            raise AppError("AI_UNAVAILABLE", "Gemini is busy and could not verify the key. Try again shortly.", 503)
        if response.is_error:
            raise AppError("AI_UNAVAILABLE", "Gemini could not verify the key. Try again shortly.", 503)

    async def locate(
        self,
        query: str,
        expected_selector: str | None,
        candidates: str,
        api_key: str | None = None,
    ) -> AIChoice:
        key = api_key or self.settings.gemini_api_key
        if not key:
            raise AppError("AI_UNAVAILABLE", "AI recovery is not configured on this server.", 503)
        prompt = (
            "Choose the one DOM candidate that best satisfies the user request. "
            "The candidates are a compact DOM sketch, not raw HTML. "
            "Only use a candidate_index from the supplied list. Do not invent selectors, values, or code. "
            "If no candidate is defensible, set found to false.\n\n"
            f"User request: {query}\n"
            f"Expected selector: {expected_selector or '(none)'}\n"
            f"Candidates: {candidates}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": AIChoice.model_json_schema(),
                "maxOutputTokens": 512,
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"
        try:
            if self.client:
                response = await self.client.post(url, json=payload, headers={"x-goog-api-key": key})
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, json=payload, headers={"x-goog-api-key": key})
        except httpx.TimeoutException as error:
            raise AppError("AI_UNAVAILABLE", "The AI service timed out. Try again shortly.", 503) from error
        except httpx.HTTPError as error:
            raise AppError("AI_UNAVAILABLE", "The AI service is unavailable. Try again shortly.", 503) from error
        self._raise_for_key_response(response)
        if response.status_code == 429:
            raise AppError("AI_UNAVAILABLE", "The AI service is busy. Try again shortly.", 503)
        if response.is_error:
            raise AppError("AI_UNAVAILABLE", "The AI service is unavailable. Try again shortly.", 503)
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return AIChoice.model_validate_json(text)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise AppError("AI_INVALID_RESPONSE", "The AI returned an unusable answer.", 502) from error

    @staticmethod
    def _raise_for_key_response(response: httpx.Response) -> None:
        if response.status_code in {400, 401, 403}:
            raise AppError(
                "INVALID_API_KEY",
                "Gemini rejected this API key. Create or copy a valid key from Google AI Studio.",
                401,
            )
