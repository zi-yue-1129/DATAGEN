"""Tests for the optional Runcrate LLM provider."""

from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.llm.factory import ProviderFactory
from src.llm.runcrate import RuncrateChatOpenAI, RuncrateProvider


def test_factory_creates_runcrate_provider() -> None:
    """The factory maps "runcrate" to the Runcrate provider and model class."""
    provider = ProviderFactory().create_provider("runcrate")

    assert isinstance(provider, RuncrateProvider)
    assert provider.get_model_class() is RuncrateChatOpenAI


def test_runcrate_model_uses_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model sends RUNCRATE_API_KEY to the Runcrate endpoint."""
    monkeypatch.setenv("RUNCRATE_API_KEY", "test-key")

    with patch("src.llm.runcrate.ChatOpenAI.__init__", return_value=None) as init:
        RuncrateChatOpenAI(model="deepseek-ai/DeepSeek-V4.1-Flash", temperature=1.0)

    init.assert_called_once_with(
        api_key=SecretStr("test-key"),
        model="deepseek-ai/DeepSeek-V4.1-Flash",
        temperature=1.0,
        base_url="https://api.runcrate.ai/v1",
    )


def test_runcrate_model_keeps_explicit_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit base_url from the model config overrides the default."""
    monkeypatch.setenv("RUNCRATE_API_KEY", "test-key")

    with patch("src.llm.runcrate.ChatOpenAI.__init__", return_value=None) as init:
        RuncrateChatOpenAI(model="zai-org/GLM-5.3", base_url="http://localhost:8080/v1")

    assert init.call_args.kwargs["base_url"] == "http://localhost:8080/v1"


def test_runcrate_model_accepts_secretstr_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SecretStr api_key is passed through as-is, not double-wrapped."""
    monkeypatch.delenv("RUNCRATE_API_KEY", raising=False)

    with patch("src.llm.runcrate.ChatOpenAI.__init__", return_value=None) as init:
        RuncrateChatOpenAI(model="zai-org/GLM-5.3", api_key=SecretStr("test-key"))

    passed_api_key = init.call_args.kwargs["api_key"]
    assert passed_api_key.get_secret_value() == "test-key"


def test_runcrate_model_requires_its_own_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing RUNCRATE_API_KEY raises instead of falling back to OPENAI_API_KEY."""
    monkeypatch.delenv("RUNCRATE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-must-not-leak")

    with pytest.raises(ValueError, match="RUNCRATE_API_KEY"):
        RuncrateChatOpenAI(model="deepseek-ai/DeepSeek-V4.1-Flash")
