from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class BaseProvider(ABC):
    """An abstract base class for LLM providers."""

    @abstractmethod
    def get_model_class(self) -> type[Any]:
        """
        Gets the model class for the provider.

        Returns:
            The class of the language model (e.g., ChatOpenAI).
        """
        pass