"""
LLM provider abstraction for the Entropy Garden agent service.

Supports:
  - local  : OpenAI-compatible endpoint (e.g. Ollama).  LOCAL_LLM_URL defaults to
             http://localhost:11434/v1 with no auth key required.
  - openrouter : OpenRouter (default remote).  Requires OPENROUTER_API_KEY.
  - openai : OpenAI API.  Requires OPENAI_API_KEY.
  - gemini : Google Gemini via its OpenAI-compatible endpoint.  Requires GEMINI_API_KEY.
  - anthropic : Anthropic API (uses the anthropic SDK).  Requires ANTHROPIC_API_KEY.

Per-role overrides: set {ROLE}_LLM_PROVIDER and/or {ROLE}_LLM_MODEL env vars.
Global defaults: LLM_PROVIDER (default: openrouter) and LLM_MODEL.

Example env var configuration:
    LLM_PROVIDER=openrouter
    LLM_MODEL=meta-llama/llama-3.1-8b-instruct
    OPENROUTER_API_KEY=sk-or-...
    ENGINEER_LLM_PROVIDER=local
    ENGINEER_LLM_MODEL=llama3.2
    LOCAL_LLM_URL=http://localhost:11434/v1
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider / model resolution
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, str] = {
    "openrouter": "meta-llama/llama-3.1-8b-instruct",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "anthropic": "claude-haiku-4-5-20251001",
    "local": "llama3.2",
}

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
_OPENAI_BASE = "https://api.openai.com/v1"
_LOCAL_LLM_DEFAULT = "http://localhost:11434/v1"


def _resolve(role: str | None) -> tuple[str, str]:
    """Return (provider, model) for a given role, respecting env var overrides."""
    prefix = f"{role.upper()}_" if role else ""

    provider = (
        os.environ.get(f"{prefix}LLM_PROVIDER")
        or os.environ.get("LLM_PROVIDER")
        or "openrouter"
    )
    model = (
        os.environ.get(f"{prefix}LLM_MODEL")
        or os.environ.get("LLM_MODEL")
        or _PROVIDER_DEFAULTS.get(provider, "")
    )
    return provider, model


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClient(Protocol):
    provider: str
    model: str

    async def complete(self, system: str, user: str) -> str:
        """Send a system + user message and return the assistant response text."""
        ...


# ---------------------------------------------------------------------------
# OpenAI-compatible client (handles local, OpenRouter, OpenAI, Gemini)
# ---------------------------------------------------------------------------


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, provider: str) -> None:
        self.provider = provider
        self.model = model
        self._base_url = base_url
        self._api_key = api_key

    async def complete(self, system: str, user: str) -> str:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
                "openai package is required for non-Anthropic providers. "
                "Install with: pip install openai"
            ) from e

        client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key or "no-key")
        log.debug("LLM call provider=%s model=%s", self.provider, self.model)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


class AnthropicClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.provider = "anthropic"
        self.model = model
        self._api_key = api_key

    async def complete(self, system: str, user: str) -> str:
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
                "anthropic package is required for the Anthropic provider. "
                "Install with: pip install anthropic"
            ) from e

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        log.debug("LLM call provider=anthropic model=%s", self.model)
        response = await client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        block = response.content[0]
        return block.text if hasattr(block, "text") else ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm_client(role: str | None = None) -> LLMClient:
    """Build and return an LLMClient for the given role (or global default if None)."""
    provider, model = _resolve(role)

    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        return AnthropicClient(api_key=key, model=model)

    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        return OpenAICompatibleClient(
            base_url=_OPENROUTER_BASE, api_key=key, model=model, provider=provider
        )

    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAICompatibleClient(
            base_url=_OPENAI_BASE, api_key=key, model=model, provider=provider
        )

    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "")
        return OpenAICompatibleClient(
            base_url=_GEMINI_BASE, api_key=key, model=model, provider=provider
        )

    if provider == "local":
        base_url = os.environ.get("LOCAL_LLM_URL", _LOCAL_LLM_DEFAULT)
        return OpenAICompatibleClient(
            base_url=base_url, api_key="no-key", model=model, provider=provider
        )

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. "
        "Valid options: local, openrouter, openai, gemini, anthropic"
    )
