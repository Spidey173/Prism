from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.facts import LLMUsage
from app.services.llm import (
    AnthropicLLMClient,
    FakeLLMClient,
    OpenAICompatibleLLMClient,
    build_llm_client,
    extract_json_payload,
)


class DummySchema(BaseModel):
    name: str
    count: int


# ============================================================================
# 1. JSON Payload Extractor Tests
# ============================================================================


def test_extract_json_payload_raw_json() -> None:
    raw = '{"name": "test", "count": 42}'
    assert extract_json_payload(raw) == raw


def test_extract_json_payload_markdown_fenced() -> None:
    raw = '```json\n{"name": "test", "count": 42}\n```'
    assert extract_json_payload(raw) == '{"name": "test", "count": 42}'


def test_extract_json_payload_conversational_wrapping() -> None:
    raw = (
        "Sure, here is the JSON data you requested:\n"
        "```json\n"
        '{"name": "test", "count": 42}\n'
        "```\n"
        "Hope this helps with your audit!"
    )
    assert extract_json_payload(raw) == '{"name": "test", "count": 42}'


def test_extract_json_payload_outer_braces_without_fence() -> None:
    raw = 'Certainly! The result is {"name": "test", "count": 42}. Have a great day.'
    assert extract_json_payload(raw) == '{"name": "test", "count": 42}'


# ============================================================================
# 2. Settings Auto-Detection & Preset Tests
# ============================================================================


def test_settings_default_openai() -> None:
    settings = Settings(_env_file=None, llm_provider="openai", llm_api_key="sk-test-key")
    assert settings.llm_provider == "openai"
    assert settings.llm_api_base == "https://api.openai.com/v1"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.llm_api_key == "sk-test-key"


def test_settings_auto_detect_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    settings = Settings(_env_file=None)
    assert settings.llm_provider == "anthropic"
    assert settings.llm_api_key == "sk-ant-test-key"
    assert settings.llm_api_base == "https://api.anthropic.com/v1"
    assert settings.llm_model == "claude-3-5-haiku-20241022"


def test_settings_auto_detect_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey")

    settings = Settings(_env_file=None)
    assert settings.llm_provider == "gemini"
    assert settings.llm_api_key == "AIzaSyTestKey"
    assert settings.llm_api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert settings.llm_model == "gemini-1.5-flash"


def test_settings_auto_detect_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")

    settings = Settings(_env_file=None)
    assert settings.llm_provider == "groq"
    assert settings.llm_api_key == "gsk-test-key"
    assert settings.llm_api_base == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "qwen/qwen3.8-27b"


def test_settings_ollama_no_key_required() -> None:
    settings = Settings(_env_file=None, llm_provider="ollama")
    assert settings.llm_provider == "ollama"
    assert settings.llm_api_key == ""
    assert settings.llm_api_base == "http://localhost:11434/v1"
    assert settings.llm_model == "llama3.2"


def test_settings_local_vllm_no_key_required() -> None:
    settings = Settings(_env_file=None, llm_provider="local", llm_api_base="http://127.0.0.1:8000/v1")
    assert settings.llm_provider == "local"
    assert settings.llm_api_key == ""
    assert settings.llm_api_base == "http://127.0.0.1:8000/v1"


# ============================================================================
# 3. Builder Client Creation Tests
# ============================================================================


def test_build_llm_client_fake() -> None:
    client = build_llm_client(Settings(_env_file=None, llm_provider="fake"))
    assert isinstance(client, FakeLLMClient)


def test_build_llm_client_ollama_without_key() -> None:
    client = build_llm_client(Settings(_env_file=None, llm_provider="ollama"))
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client.settings.llm_api_base == "http://localhost:11434/v1"


def test_build_llm_client_gemini() -> None:
    client = build_llm_client(Settings(_env_file=None, llm_provider="gemini", llm_api_key="AIzaSy123"))
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert "generativelanguage.googleapis.com" in client.settings.llm_api_base


def test_build_llm_client_anthropic() -> None:
    client = build_llm_client(Settings(_env_file=None, llm_provider="anthropic", llm_api_key="sk-ant-123"))
    assert isinstance(client, AnthropicLLMClient)
    assert client.settings.llm_model == "claude-3-5-haiku-20241022"


def test_build_llm_client_missing_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    settings = Settings(_env_file=None, llm_provider="openai", llm_api_key="")

    with pytest.raises(ValueError, match="No API key found for LLM_PROVIDER='openai'"):
        build_llm_client(settings)


# ============================================================================
# 4. Mocked API Execution & Usage Callback Tests
# ============================================================================


def test_openai_compatible_complete_json_success() -> None:
    settings = Settings(
        llm_provider="openai",
        llm_api_key="sk-mock",
        llm_input_usd_per_million=Decimal("1.50"),
        llm_output_usd_per_million=Decimal("2.00"),
    )
    recorded_usage: list[LLMUsage] = []

    mock_response = {
        "choices": [
            {"message": {"content": '```json\n{"name": "Alpha", "count": 100}\n```'}}
        ],
        "usage": {"prompt_tokens": 500, "completion_tokens": 50},
    }

    mock_urlopen = MagicMock()
    mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(mock_response).encode()

    with patch("app.services.llm.urlopen", mock_urlopen):
        client = OpenAICompatibleLLMClient(settings, usage_callback=recorded_usage.append)
        result = client.complete_json("system instructions", "prompt message", DummySchema)

    assert result.name == "Alpha"
    assert result.count == 100
    assert len(recorded_usage) == 1
    assert recorded_usage[0].input_tokens == 500
    assert recorded_usage[0].output_tokens == 50
    assert recorded_usage[0].cost_usd > Decimal("0")


def test_openai_compatible_retries_without_response_format_on_400() -> None:
    settings = Settings(llm_provider="ollama", llm_api_key="")

    # First call returns 400 Bad Request regarding response_format
    err_body = b'{"error": "Unsupported param: response_format"}'
    err_400 = HTTPError(
        url="http://localhost:11434/v1/chat/completions",
        code=400,
        msg="Bad Request",
        hdrs={},  # type: ignore[arg-type]
        fp=BytesIO(err_body),
    )

    success_response = {
        "choices": [{"message": {"content": '{"name": "LocalModel", "count": 77}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }

    mock_file = MagicMock()
    mock_file.read.return_value = json.dumps(success_response).encode()
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_file

    mock_urlopen = MagicMock(side_effect=[err_400, mock_context])

    with patch("app.services.llm.urlopen", mock_urlopen):
        client = OpenAICompatibleLLMClient(settings)
        assert client.supports_response_format is True

        result = client.complete_json("system instructions", "prompt message", DummySchema)

        assert result.name == "LocalModel"
        assert result.count == 77
        # Verify that client learned response_format is unsupported and disabled it
        assert client.supports_response_format is False


def test_anthropic_complete_json_success() -> None:
    settings = Settings(
        llm_provider="anthropic",
        llm_api_key="sk-ant-test",
        llm_input_usd_per_million=Decimal("0.80"),
        llm_output_usd_per_million=Decimal("4.00"),
    )
    recorded_usage: list[LLMUsage] = []

    anthropic_payload = {
        "content": [
            {
                "type": "text",
                "text": "Here is the result:\n```json\n{\"name\": \"Claude\", \"count\": 99}\n```",
            }
        ],
        "usage": {"input_tokens": 300, "output_tokens": 40},
    }

    mock_urlopen = MagicMock()
    mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(anthropic_payload).encode()

    with patch("app.services.llm.urlopen", mock_urlopen):
        client = AnthropicLLMClient(settings, usage_callback=recorded_usage.append)
        result = client.complete_json("system prompt", "user query", DummySchema)

    assert result.name == "Claude"
    assert result.count == 99
    assert len(recorded_usage) == 1
    assert recorded_usage[0].input_tokens == 300
    assert recorded_usage[0].output_tokens == 40

