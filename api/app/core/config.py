import os
from functools import lru_cache
from decimal import Decimal
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "requires_key": True,
        "env_keys": ["OPENAI_API_KEY", "LLM_API_KEY"],
    },
    "gemini": {
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-1.5-flash",
        "requires_key": True,
        "env_keys": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"],
    },
    "google": {
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-1.5-flash",
        "requires_key": True,
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"],
    },
    "anthropic": {
        "api_base": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "requires_key": True,
        "env_keys": ["ANTHROPIC_API_KEY", "LLM_API_KEY"],
    },
    "claude": {
        "api_base": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "requires_key": True,
        "env_keys": ["ANTHROPIC_API_KEY", "LLM_API_KEY"],
    },
    "groq": {
        "api_base": "https://api.groq.com/openai/v1",
        "default_model": "qwen/qwen3.8-27b",
        "requires_key": True,
        "env_keys": ["GROQ_API_KEY", "LLM_API_KEY"],
    },
    "openrouter": {
        "api_base": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
        "requires_key": True,
        "env_keys": ["OPENROUTER_API_KEY", "LLM_API_KEY"],
    },
    "ollama": {
        "api_base": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "requires_key": False,
        "env_keys": ["OLLAMA_API_KEY", "LLM_API_KEY"],
    },
    "local": {
        "api_base": "http://localhost:8000/v1",
        "default_model": "local-model",
        "requires_key": False,
        "env_keys": ["LOCAL_API_KEY", "LLM_API_KEY"],
    },
    "vllm": {
        "api_base": "http://localhost:8000/v1",
        "default_model": "default",
        "requires_key": False,
        "env_keys": ["VLLM_API_KEY", "LLM_API_KEY"],
    },
    "lmstudio": {
        "api_base": "http://localhost:1234/v1",
        "default_model": "default",
        "requires_key": False,
        "env_keys": ["LMSTUDIO_API_KEY", "LLM_API_KEY"],
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "requires_key": True,
        "env_keys": ["DEEPSEEK_API_KEY", "LLM_API_KEY"],
    },
    "mistral": {
        "api_base": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "requires_key": True,
        "env_keys": ["MISTRAL_API_KEY", "LLM_API_KEY"],
    },
    "together": {
        "api_base": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "requires_key": True,
        "env_keys": ["TOGETHER_API_KEY", "LLM_API_KEY"],
    },
    "azure": {
        "api_base": "",
        "default_model": "gpt-4o-mini",
        "requires_key": True,
        "env_keys": ["AZURE_OPENAI_API_KEY", "AZURE_API_KEY", "LLM_API_KEY"],
    },
    "fake": {
        "api_base": "",
        "default_model": "fake-model",
        "requires_key": False,
        "env_keys": [],
    },
    "mock": {
        "api_base": "",
        "default_model": "mock-model",
        "requires_key": False,
        "env_keys": [],
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg:///auditor?port=5433"
    upload_dir: str = "./data/uploads"
    embedding_dim: int = 384
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    max_upload_bytes: int = 50_000_000
    max_pdf_pages: int = 500
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_input_usd_per_million: Decimal = Decimal("0")
    llm_output_usd_per_million: Decimal = Decimal("0")
    llm_max_cost_per_audit_usd: Decimal = Decimal("0.50")
    llm_max_output_tokens: int = 1200
    llm_timeout_seconds: int = 90
    semantic_top_k: int = 5
    semantic_similarity_threshold: float = 0.70
    semantic_min_chunk_distance: int = 12
    semantic_max_pairs_per_audit: int = 50
    semantic_confidence_threshold: float = 0.75

    @model_validator(mode="before")
    @classmethod
    def resolve_llm_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            data = {}

        provider = (data.get("llm_provider") or os.getenv("LLM_PROVIDER") or "").strip().lower()
        key = data.get("llm_api_key") or os.getenv("LLM_API_KEY") or ""

        # Auto-detect provider if default 'openai' was not explicitly intended with an OpenAI key
        if not provider or provider == "openai":
            if not key and not os.getenv("OPENAI_API_KEY"):
                if os.getenv("ANTHROPIC_API_KEY"):
                    provider = "anthropic"
                elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
                    provider = "gemini"
                elif os.getenv("GROQ_API_KEY"):
                    provider = "groq"
                elif os.getenv("OPENROUTER_API_KEY"):
                    provider = "openrouter"
                elif os.getenv("DEEPSEEK_API_KEY"):
                    provider = "deepseek"
                elif os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_API_BASE"):
                    provider = "ollama"
        if not provider:
            provider = "openai"
        data["llm_provider"] = provider

        preset = PROVIDER_PRESETS.get(provider, {})

        # Resolve API key if not supplied
        if not key:
            for env_name in preset.get("env_keys", []):
                val = os.getenv(env_name)
                if val:
                    key = val
                    break
            if not key:
                for env_name in (
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "GEMINI_API_KEY",
                    "GOOGLE_API_KEY",
                    "GROQ_API_KEY",
                    "OPENROUTER_API_KEY",
                    "DEEPSEEK_API_KEY",
                ):
                    val = os.getenv(env_name)
                    if val:
                        key = val
                        break
        data["llm_api_key"] = key

        # Resolve API base
        api_base = data.get("llm_api_base") or os.getenv("LLM_API_BASE")
        known_preset_bases = {p["api_base"] for p in PROVIDER_PRESETS.values() if p.get("api_base")}
        if not api_base or api_base in known_preset_bases:
            if provider == "ollama":
                api_base = (
                    os.getenv("OLLAMA_API_BASE")
                    or os.getenv("OLLAMA_HOST")
                    or preset.get("api_base", "http://localhost:11434/v1")
                )
                if not api_base.endswith("/v1"):
                    api_base = f"{api_base.rstrip('/')}/v1"
            elif preset.get("api_base"):
                api_base = preset["api_base"]
        if api_base:
            data["llm_api_base"] = api_base

        # Resolve Model
        model = data.get("llm_model") or os.getenv("LLM_MODEL")
        known_preset_models = {p["default_model"] for p in PROVIDER_PRESETS.values() if p.get("default_model")}
        if not model or model in known_preset_models:
            if preset.get("default_model"):
                model = preset["default_model"]
        if model:
            data["llm_model"] = model

        # If provider does not require key (ollama, local, fake), do not force a key from .env unless explicitly given
        if not preset.get("requires_key", True) and "llm_api_key" not in data:
            data["llm_api_key"] = ""

        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
