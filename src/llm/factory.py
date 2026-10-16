from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .anthropic import AnthropicProvider
from .atlascloud import AtlasCloudProvider
from .azure import AzureChatOpenAIProvider
from .cheaperinference import CheaperInferenceProvider
from .google import GoogleProvider
from .groq import ChatGroqProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .orcarouter import OrcaRouterProvider

if TYPE_CHECKING:
    from .base import BaseProvider


class ProviderFactory:
    """A factory class for creating LLM providers."""

    def create_provider(self, provider_name: str, **kwargs: Any) -> BaseProvider:
        """
        Creates a provider instance based on the provider name.

        Args:
            provider_name: The name of the provider to create.
            **kwargs: Additional keyword arguments for provider configuration.

        Returns:
            An instance of the requested provider.

        Raises:
            NotImplementedError: If the provider creation is not implemented.
        """
        if provider_name == "openai":
            return OpenAIProvider()
        elif provider_name == "anthropic":
            return AnthropicProvider()
        elif provider_name == "google":
            return GoogleProvider()
        elif provider_name == "ollama":
            return OllamaProvider()
        elif provider_name == "azure":
            return AzureChatOpenAIProvider()
        elif provider_name == "groq":
            return ChatGroqProvider()
        elif provider_name == "atlascloud":
            return AtlasCloudProvider()
        elif provider_name == "orcarouter":
            return OrcaRouterProvider()
        elif provider_name == "cheaperinference":
            return CheaperInferenceProvider()
        else:
            raise NotImplementedError(
                f"Provider creation for '{provider_name}' is not implemented."
            )
