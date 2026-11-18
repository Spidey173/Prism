from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Callable, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from app.core.config import PROVIDER_PRESETS, Settings
from app.schemas.facts import LLMUsage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
UsageCallback = Callable[[LLMUsage], None]


def extract_json_payload(raw: str) -> str:
    """Extract clean JSON string from raw model text, stripping markdown blocks or conversational noise."""
    cleaned = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace : last_brace + 1].strip()

    return cleaned


class LLMClient(Protocol):
    def complete_json(self, system: str, prompt: str, schema: type[T]) -> T: ...


class OpenAICompatibleLLMClient:
    """Universal client for any OpenAI-compatible API (OpenAI, Gemini, Groq, Ollama, vLLM, OpenRouter, DeepSeek, etc.)."""

    def __init__(self, settings: Settings, usage_callback: UsageCallback | None = None) -> None:
        self.settings = settings
        self.usage_callback = usage_callback
        self.supports_response_format = True

    def complete_json(self, system: str, prompt: str, schema: type[T]) -> T:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        current_prompt = f"Return one JSON object matching this schema exactly:\n{schema_json}\n\n{prompt}"
        api_base = self.settings.llm_api_base.rstrip("/")
        endpoint = api_base if api_base.endswith("/chat/completions") else f"{api_base}/chat/completions"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Prism/1.0 (AuditEngine; +https://github.com/)",
        }
        if self.settings.llm_api_key:
            if self.settings.llm_provider.lower() == "azure":
                headers["api-key"] = self.settings.llm_api_key
            else:
                headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        last_error: Exception | None = None
        timeout = getattr(self.settings, "llm_timeout_seconds", 90)

        for attempt in range(3):
            body: dict[str, Any] = {
                "model": self.settings.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": current_prompt},
                ],
                "max_tokens": self.settings.llm_max_output_tokens,
            }
            if self.supports_response_format:
                body["response_format"] = {"type": "json_object"}

            request = Request(
                endpoint,
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
            except HTTPError as exc:
                err_text = ""
                try:
                    err_text = exc.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                if exc.code == 400 and self.supports_response_format and "response_format" in err_text.lower():
                    self.supports_response_format = False
                    continue
                raise RuntimeError(f"LLM HTTP {exc.code} request failed: {exc.reason} - {err_text[:300]}") from exc
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(f"LLM request connection failed: {exc}") from exc

            usage = payload.get("usage", {})
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
            cost = (
                Decimal(input_tokens) * self.settings.llm_input_usd_per_million
                + Decimal(output_tokens) * self.settings.llm_output_usd_per_million
            ) / Decimal(1_000_000)
            if self.usage_callback:
                self.usage_callback(
                    LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
                )

            try:
                choices = payload.get("choices", [])
                if not choices:
                    raise ValueError(f"Provider returned no choices in response: {payload}")
                content = choices[0]["message"]["content"]
                if not isinstance(content, str):
                    raise ValueError("The provider returned an empty or non-string message content.")
                extracted = extract_json_payload(content)
                return schema.model_validate_json(extracted)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                current_prompt += (
                    "\n\nYour previous response was invalid. Return ONLY valid JSON matching the schema. "
                    f"Validation error: {str(exc)[:1200]}"
                )
        raise ValueError(f"LLM returned invalid JSON after 2 retries: {last_error}")


class AnthropicLLMClient:
    """Client for Anthropic Claude native Messages API."""

    def __init__(self, settings: Settings, usage_callback: UsageCallback | None = None) -> None:
        self.settings = settings
        self.usage_callback = usage_callback

    def complete_json(self, system: str, prompt: str, schema: type[T]) -> T:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        current_prompt = f"Return one JSON object matching this schema exactly:\n{schema_json}\n\n{prompt}"
        api_base = (self.settings.llm_api_base or "https://api.anthropic.com/v1").rstrip("/")
        endpoint = api_base if api_base.endswith("/messages") else f"{api_base}/messages"

        headers: dict[str, str] = {
            "x-api-key": self.settings.llm_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "Prism/1.0 (AuditEngine; +https://github.com/)",
        }

        last_error: Exception | None = None
        timeout = getattr(self.settings, "llm_timeout_seconds", 90)

        for attempt in range(3):
            body = {
                "model": self.settings.llm_model,
                "system": system,
                "messages": [
                    {"role": "user", "content": current_prompt},
                ],
                "max_tokens": self.settings.llm_max_output_tokens,
            }
            request = Request(
                endpoint,
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
            except HTTPError as exc:
                err_text = ""
                try:
                    err_text = exc.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                raise RuntimeError(f"Anthropic HTTP {exc.code} request failed: {exc.reason} - {err_text[:300]}") from exc
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(f"Anthropic request failed: {exc}") from exc

            usage = payload.get("usage", {})
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            cost = (
                Decimal(input_tokens) * self.settings.llm_input_usd_per_million
                + Decimal(output_tokens) * self.settings.llm_output_usd_per_million
            ) / Decimal(1_000_000)
            if self.usage_callback:
                self.usage_callback(
                    LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
                )

            try:
                content_blocks = payload.get("content", [])
                text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                content = "".join(text_parts).strip()
                if not content:
                    raise ValueError("Anthropic returned an empty response body.")
                extracted = extract_json_payload(content)
                return schema.model_validate_json(extracted)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                current_prompt += (
                    "\n\nYour previous response was invalid. Return ONLY valid JSON matching the schema. "
                    f"Validation error: {str(exc)[:1200]}"
                )
        raise ValueError(f"Anthropic LLM returned invalid JSON after 2 retries: {last_error}")


class FakeLLMClient:
    """Deterministic test client; each call consumes one canned response."""

    def __init__(
        self,
        responses: Sequence[dict[str, Any] | BaseModel | str] = (),
        handler: Callable[[str, type[BaseModel]], dict[str, Any] | BaseModel | str] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.handler = handler
        self.calls = 0

    def complete_json(self, system: str, prompt: str, schema: type[T]) -> T:
        del system
        self.calls += 1
        last_error: Exception | None = None
        for _attempt in range(3):
            if self.responses:
                value: dict[str, Any] | BaseModel | str = self.responses.pop(0)
            elif self.handler is not None:
                value = self.handler(prompt, schema)
            else:
                value = {"facts": []} if schema.__name__ == "FactExtractionResponse" else {"judgments": []}
            if isinstance(value, BaseModel):
                value = value.model_dump(mode="json")
            try:
                if isinstance(value, str):
                    extracted = extract_json_payload(value)
                    return schema.model_validate_json(extracted)
                return schema.model_validate(value)
            except (ValueError, ValidationError) as exc:
                last_error = exc
        raise ValueError(f"Fake LLM returned invalid JSON after 2 retries: {last_error}")


def build_llm_client(settings: Settings, usage_callback: UsageCallback | None = None) -> LLMClient:
    """Build the appropriate LLM client based on the provider in settings."""
    provider = settings.llm_provider.lower().strip()

    # 1. Deterministic test clients
    if provider in ("fake", "mock", "test"):
        return FakeLLMClient([])

    # 2. Anthropic native client
    if provider in ("anthropic", "claude"):
        if not settings.llm_api_key:
            if "CI" in os.environ or "PYTEST_CURRENT_TEST" in os.environ:
                logger.warning("No ANTHROPIC_API_KEY found in CI/Test environment; falling back to FakeLLMClient.")
                return FakeLLMClient([])
            raise ValueError(
                "API key required for Anthropic. Set ANTHROPIC_API_KEY or LLM_API_KEY in your environment."
            )
        return AnthropicLLMClient(settings, usage_callback)

    # 3. All OpenAI-compatible clients (OpenAI, Gemini, Groq, Ollama, Local, vLLM, OpenRouter, DeepSeek, etc.)
    preset = PROVIDER_PRESETS.get(provider, {})
    requires_key = preset.get("requires_key", True)

    if requires_key and not settings.llm_api_key:
        if "CI" in os.environ or "PYTEST_CURRENT_TEST" in os.environ:
            logger.warning("No LLM API key found in CI/Test environment; falling back to FakeLLMClient.")
            return FakeLLMClient([])
        raise ValueError(
            f"No API key found for LLM_PROVIDER='{settings.llm_provider}'.\n"
            "Configure one of the following in your environment or .env file:\n"
            "  - OpenAI:       export OPENAI_API_KEY=sk-... (or LLM_API_KEY=...)\n"
            "  - Gemini:       export GEMINI_API_KEY=AIza... (or GOOGLE_API_KEY=...)\n"
            "  - Anthropic:    export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  - Groq:         export GROQ_API_KEY=gsk_...\n"
            "  - OpenRouter:   export OPENROUTER_API_KEY=sk-or-...\n"
            "  - DeepSeek:     export DEEPSEEK_API_KEY=sk-...\n"
            "  - Ollama/Local: export LLM_PROVIDER=ollama (no API key required!)\n"
            "  - Custom URL:   export LLM_API_BASE=http://localhost:8000/v1 LLM_PROVIDER=local\n"
            "  - Tests/Mock:   export LLM_PROVIDER=fake"
        )

    return OpenAICompatibleLLMClient(settings, usage_callback)
