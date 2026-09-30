"""
LLM provider abstraction for the AeroTwin Copilot.

One RAG pipeline (copilot_engine.py) builds a system prompt + user prompt
once, then hands them to whichever provider is configured — the
providers below don't know about RAG, ChromaDB, or the intent router at
all; they only know how to turn (system_prompt, user_prompt) into text.
That's deliberate: duplicating retrieval/context logic per-provider is
exactly the "Groq RAG / Gemini RAG / Ollama RAG" anti-pattern the spec
this was built against explicitly calls out.

Each provider raises `LLMProviderError`, never a raw SDK exception, so
callers (copilot_engine.py's fallback chain, copilot.py's error
responses) can rely on `.category` instead of introspecting
provider-specific exception types.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorCategory:
    NOT_CONFIGURED = "not_configured"      # missing/empty API key for this provider
    INVALID_KEY = "invalid_key"
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"             # provider's servers are down/overloaded
    INVALID_MODEL = "invalid_model"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    UNKNOWN = "unknown"


class LLMProviderError(Exception):
    """Raised by every provider instead of letting a raw SDK exception escape.

    `category` drives copilot.py's safe, differentiated user-facing message;
    `technical_detail` is for server-side logs only and must never be sent
    to the client (it may include SDK error bodies).
    """

    def __init__(self, category: str, technical_detail: str):
        self.category = category
        self.technical_detail = technical_detail
        super().__init__(f"[{category}] {technical_detail}")


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_s: float


class LLMProvider:
    """Base interface every provider implements."""

    name: str = "base"

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResult:
        raise NotImplementedError


class GroqProvider(LLMProvider):
    """Groq's OpenAI-compatible chat completions endpoint, called with
    plain httpx — the project already depends on httpx, and Groq's API
    is a simple enough REST call that adding the `openai` SDK just for
    this would be exactly the "unnecessary dependency" the spec warns
    against."""

    name = "groq"
    _BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: Optional[str], model: str):
        if not api_key:
            raise LLMProviderError(ErrorCategory.NOT_CONFIGURED, "GROQ_API_KEY is not set")
        self._api_key = api_key
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResult:
        import httpx

        started = time.monotonic()
        try:
            resp = httpx.post(
                self._BASE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                },
                timeout=30.0,
            )
        except httpx.TimeoutException as e:
            raise LLMProviderError(ErrorCategory.TIMEOUT, f"Groq request timed out: {e}")
        except httpx.HTTPError as e:
            raise LLMProviderError(ErrorCategory.UNAVAILABLE, f"Groq connection error: {e}")

        if resp.status_code == 401:
            raise LLMProviderError(ErrorCategory.INVALID_KEY, f"Groq 401: {resp.text}")
        if resp.status_code == 404:
            raise LLMProviderError(ErrorCategory.INVALID_MODEL, f"Groq 404 (bad model '{self._model}'): {resp.text}")
        if resp.status_code == 429:
            raise LLMProviderError(ErrorCategory.QUOTA_EXCEEDED, f"Groq 429: {resp.text}")
        if resp.status_code >= 500:
            raise LLMProviderError(ErrorCategory.UNAVAILABLE, f"Groq {resp.status_code}: {resp.text}")
        if resp.status_code >= 400:
            raise LLMProviderError(ErrorCategory.UNKNOWN, f"Groq {resp.status_code}: {resp.text}")

        try:
            body = resp.json()
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
        except (KeyError, IndexError, ValueError) as e:
            raise LLMProviderError(ErrorCategory.MALFORMED_RESPONSE, f"Groq response parse error: {e}; body={resp.text[:500]}")

        if not text or not text.strip():
            raise LLMProviderError(ErrorCategory.EMPTY_RESPONSE, "Groq returned an empty completion")

        return LLMResult(
            text=text,
            provider=self.name,
            model=self._model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_s=time.monotonic() - started,
        )


class GeminiProvider(LLMProvider):
    """Raw `google-genai` SDK — no langchain wrapper. langchain-google-genai
    was the original implementation's chat model, but keeping it would
    mean each provider speaks a different interface (langchain Message
    objects vs plain strings); the embeddings step (ChromaDB's retriever)
    still uses `langchain_google_genai.GoogleGenerativeAIEmbeddings`
    unchanged — only the chat/generation call moved to the plain SDK so
    every provider implements the same generate(system, user) contract."""

    name = "gemini"

    def __init__(self, api_key: Optional[str], model: str):
        if not api_key:
            raise LLMProviderError(ErrorCategory.NOT_CONFIGURED, "GEMINI_API_KEY is not set")
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResult:
        from google.genai import errors as genai_errors
        from google.genai import types as genai_types

        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(system_instruction=system_prompt, temperature=0),
            )
        except genai_errors.ClientError as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or getattr(e, "code", None) == 429:
                raise LLMProviderError(ErrorCategory.QUOTA_EXCEEDED, msg)
            if "API_KEY_INVALID" in msg or getattr(e, "code", None) == 401 or getattr(e, "code", None) == 403:
                raise LLMProviderError(ErrorCategory.INVALID_KEY, msg)
            if "NOT_FOUND" in msg:
                raise LLMProviderError(ErrorCategory.INVALID_MODEL, msg)
            raise LLMProviderError(ErrorCategory.UNKNOWN, msg)
        except genai_errors.ServerError as e:
            raise LLMProviderError(ErrorCategory.UNAVAILABLE, str(e))
        except TimeoutError as e:
            raise LLMProviderError(ErrorCategory.TIMEOUT, str(e))

        text = getattr(response, "text", None)
        if not text or not text.strip():
            raise LLMProviderError(ErrorCategory.EMPTY_RESPONSE, "Gemini returned an empty completion")

        usage = getattr(response, "usage_metadata", None)
        return LLMResult(
            text=text,
            provider=self.name,
            model=self._model,
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            latency_s=time.monotonic() - started,
        )


class OllamaProvider(LLMProvider):
    """Local model via Ollama's REST API — no external API key, so it
    works with zero quota once a model is pulled locally. Optional: only
    reachable if an Ollama server is actually running."""

    name = "ollama"

    def __init__(self, base_url: str, model: Optional[str]):
        if not model:
            raise LLMProviderError(ErrorCategory.NOT_CONFIGURED, "OLLAMA_MODEL is not set")
        self._base_url = base_url.rstrip("/")
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResult:
        import httpx

        started = time.monotonic()
        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=60.0,
            )
        except httpx.TimeoutException as e:
            raise LLMProviderError(ErrorCategory.TIMEOUT, f"Ollama request timed out: {e}")
        except httpx.HTTPError as e:
            raise LLMProviderError(ErrorCategory.UNAVAILABLE, f"Ollama unreachable at {self._base_url}: {e}")

        if resp.status_code == 404:
            raise LLMProviderError(ErrorCategory.INVALID_MODEL, f"Ollama model '{self._model}' not found: {resp.text}")
        if resp.status_code >= 400:
            raise LLMProviderError(ErrorCategory.UNKNOWN, f"Ollama {resp.status_code}: {resp.text}")

        try:
            body = resp.json()
            text = body["message"]["content"]
        except (KeyError, ValueError) as e:
            raise LLMProviderError(ErrorCategory.MALFORMED_RESPONSE, f"Ollama response parse error: {e}; body={resp.text[:500]}")

        if not text or not text.strip():
            raise LLMProviderError(ErrorCategory.EMPTY_RESPONSE, "Ollama returned an empty completion")

        return LLMResult(
            text=text,
            provider=self.name,
            model=self._model,
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            latency_s=time.monotonic() - started,
        )


def build_provider(name: str, settings) -> LLMProvider:
    """Factory — settings is app.core.config.settings, passed in rather
    than imported here so this module has no dependency on the FastAPI
    app's config location (keeps it usable standalone, e.g. from tests)."""
    if name == "groq":
        return GroqProvider(settings.GROQ_API_KEY, settings.GROQ_MODEL)
    if name == "gemini":
        return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    if name == "ollama":
        return OllamaProvider(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    raise LLMProviderError(ErrorCategory.NOT_CONFIGURED, f"Unknown LLM_PROVIDER '{name}'")
