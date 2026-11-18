from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .base import BaseProvider

# Runcrate serves open-weight models through an OpenAI-compatible API. Model
# IDs use the "<org>/<model>" form (e.g. deepseek-ai/DeepSeek-V4.1-Flash).
RUNCRATE_BASE_URL = "https://api.runcrate.ai/v1"


class RuncrateChatOpenAI(ChatOpenAI):
    """ChatOpenAI preconfigured for the Runcrate inference API."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the client with Runcrate credentials and endpoint.

        Args:
            **kwargs: ChatOpenAI keyword arguments from the agent model config.
                An explicit ``api_key`` or ``base_url`` overrides the defaults.

        Raises:
            ValueError: If no API key is passed and ``RUNCRATE_API_KEY`` is
                unset. Passing ``api_key=None`` through would make the OpenAI
                SDK fall back to ``OPENAI_API_KEY`` and send it to Runcrate.
        """
        api_key = kwargs.pop("api_key", None) or os.getenv("RUNCRATE_API_KEY")
        if not api_key:
            raise ValueError("RUNCRATE_API_KEY is required for the Runcrate provider")

        kwargs.setdefault("base_url", RUNCRATE_BASE_URL)
        if isinstance(api_key, str):
            api_key = SecretStr(api_key)
        super().__init__(api_key=api_key, **kwargs)


class RuncrateProvider(BaseProvider):
    """Provider for Runcrate models."""

    def get_model_class(self) -> type:
        """Returns the RuncrateChatOpenAI class."""
        return RuncrateChatOpenAI
