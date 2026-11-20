"""Picks the AI provider from settings."""
from functools import lru_cache

from app.ai.providers.base import AIOutputError, AIProvider, AIUnavailable
from app.core.config import get_settings

__all__ = ["AIOutputError", "AIProvider", "AIUnavailable", "get_provider"]


@lru_cache
def get_provider() -> AIProvider:
    s = get_settings()
    choice = s.ai_provider.lower()
    if choice == "anthropic" or (choice == "auto" and s.anthropic_api_key):
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.ai_timeout_seconds)
    from app.ai.providers.mock import MockProvider

    return MockProvider()
