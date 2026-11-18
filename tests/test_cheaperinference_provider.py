"""Tests for the optional Cheaper Inference LLM provider."""

from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.llm.cheaperinference import (
    CheaperInferenceChatOpenAI,
    CheaperInferenceProvider,
)
from src.llm.factory import ProviderFactory


def test_factory_creates_cheaperinference_provider() -> None:
    """The factory maps "cheaperinference" to the Cheaper Inference provider and model class."""
    provider = ProviderFactory().create_provider("cheaperinference")

    assert isinstance(provider, CheaperInferenceProvider)
    assert provider.get_model_class() is CheaperInferenceChatOpenAI


def test_cheaperinference_model_uses_compatible_endpoint_with_default_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model targets Cheaper Inference and keeps ChatOpenAI's default retry policy."""
    monkeypatch.setenv("CHEAPER_INFERENCE_API_KEY", "test-key")

    with patch(
        "src.llm.cheaperinference.ChatOpenAI.__init__", return_value=None
    ) as init:
        CheaperInferenceChatOpenAI(model="gpt-5.4-mini", temperature=1.0)

    init.assert_called_once_with(
        api_key=SecretStr("test-key"),
        model="gpt-5.4-mini",
        temperature=1.0,
        base_url="https://api.cheaperinference.com/v1",
    )


def test_cheaperinference_model_accepts_secretstr_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SecretStr api_key is passed through as-is, not double-wrapped."""
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)

    with patch(
        "src.llm.cheaperinference.ChatOpenAI.__init__", return_value=None
    ) as init:
        CheaperInferenceChatOpenAI(model="gpt-5.4-mini", api_key=SecretStr("test-key"))

    passed_api_key = init.call_args.kwargs["api_key"]
    assert passed_api_key.get_secret_value() == "test-key"


def test_cheaperinference_model_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing CHEAPER_INFERENCE_API_KEY raises instead of silently using another key."""
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="CHEAPER_INFERENCE_API_KEY"):
        CheaperInferenceChatOpenAI(model="gpt-5.4-mini")
