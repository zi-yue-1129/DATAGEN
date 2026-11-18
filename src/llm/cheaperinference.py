from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .base import BaseProvider


class CheaperInferenceChatOpenAI(ChatOpenAI):
    """ChatOpenAI client configured for Cheaper Inference's compatible API."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the client with Cheaper Inference credentials and endpoint.

        Args:
            **kwargs: ChatOpenAI keyword arguments from the agent model config.
                An explicit ``api_key`` or ``base_url`` overrides the defaults.

        Raises:
            ValueError: If no API key is passed and ``CHEAPER_INFERENCE_API_KEY``
                is unset.
        """
        api_key = kwargs.pop("api_key", None) or os.getenv("CHEAPER_INFERENCE_API_KEY")
        if not api_key:
            raise ValueError(
                "CHEAPER_INFERENCE_API_KEY is required for the Cheaper Inference provider"
            )

        kwargs.setdefault("base_url", "https://api.cheaperinference.com/v1")
        if isinstance(api_key, str):
            api_key = SecretStr(api_key)
        super().__init__(api_key=api_key, **kwargs)


class CheaperInferenceProvider(BaseProvider):
    """Provider for models exposed by Cheaper Inference."""

    def get_model_class(self) -> type[Any]:
        """Returns the Cheaper Inference ChatOpenAI class."""
        return CheaperInferenceChatOpenAI
