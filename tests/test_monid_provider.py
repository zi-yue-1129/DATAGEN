"""Tests for optional Monid extraction, isolated from application startup."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
import requests

TOOLS = Path(__file__).resolve().parents[1] / "src" / "tools"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def monid(monkeypatch):
    monkeypatch.setenv("MONID_API_KEY", "test-key")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("CRW_API_KEY", raising=False)
    module = load_module("_monid_under_test", TOOLS / "monid.py")
    monkeypatch.setattr(module.requests, "post", Mock())
    monkeypatch.setattr(module.requests, "get", Mock())
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


def test_monid_request_and_result_with_only_monid_key(monid):
    monid.requests.post.return_value = response(
        {"output": {"result": {"content": "网页内容"}}}
    )
    assert monid.monid(["https://example.com/中文"]) == "网页内容"
    args, kwargs = monid.requests.post.call_args
    assert args == ("https://api.monid.ai/v1/run",)
    assert kwargs["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = json.loads(kwargs["data"].decode("utf-8"))
    assert payload == {
        "provider": "tinyfish",
        "endpoint": "/automation/run",
        "input": {
            "queryParams": {},
            "pathParams": {},
            "body": {
                "url": "https://example.com/中文",
                "goal": "Extract the main text content of this webpage as content.",
                "output_schema": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}},
                    "required": ["content"],
                },
            },
        },
    }
    assert "中文".encode() in kwargs["data"]
    monid.requests.get.assert_not_called()


def test_async_polling(monid):
    monid.requests.post.return_value = response({"runId": "run-1"}, 202)
    monid.requests.get.side_effect = [
        response({"status": "RUNNING"}),
        response({"status": "COMPLETED", "output": {"result": {"content": "text"}}}),
    ]
    assert monid.monid(["https://example.com"]) == "text"
    assert monid.requests.get.call_count == 2
    assert monid.requests.get.call_args.args == (
        "https://api.monid.ai/v1/runs/run-1",
    )
    assert monid.requests.get.call_args.kwargs["headers"] == {
        "Authorization": "Bearer test-key"
    }


@pytest.mark.parametrize("status", [400, 404, 429])
def test_provider_errors_use_tool_error_result(monid, status):
    monid.requests.post.return_value = response({
        "status": "COMPLETED",
        "providerResponse": {"httpStatus": status, "error": "vendor error"},
    })
    assert monid.monid(["https://example.com"]) == (
        f"Error: TinyFish error {status}: vendor error"
    )


@pytest.mark.parametrize("status", ["FAILED", "TIMED_OUT", "STOPPED", "BLOCKED"])
def test_terminal_failure(monid, status):
    monid.requests.post.return_value = response({"status": status})
    assert monid.monid(["https://example.com"]) == f"Error: Monid run {status}"


def test_poll_http_error(monid):
    monid.requests.post.return_value = response({"runId": "run-1"}, 202)
    monid.requests.get.return_value.raise_for_status.side_effect = requests.HTTPError(
        "bad key"
    )
    assert monid.monid(["https://example.com"]) == "Error: bad key"


def test_poll_deadline(monid, monkeypatch):
    monid.requests.post.return_value = response({"runId": "run-1"}, 202)
    monkeypatch.setattr(monid.time, "monotonic", Mock(side_effect=[0, 301]))
    assert monid.monid(["https://example.com"]) == "Error: Monid run timed out"
    monid.requests.get.assert_not_called()


def test_invalid_provider_result(monid):
    monid.requests.post.return_value = response({"output": {"result": {"status": "failed"}}})
    assert monid.monid(["https://example.com"]) == (
        "Error: TinyFish did not return webpage content"
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_factory_registration_preserves_existing_tools(monkeypatch, enabled):
    # Stub unrelated integrations, as in the isolated core-module tests.
    if enabled:
        monkeypatch.setenv("MONID_API_KEY", "test-key")
    else:
        monkeypatch.delenv("MONID_API_KEY", raising=False)
    dependencies = {
        "langchain.tools": ["BaseTool"],
        "langchain_community.agent_toolkits.load_tools": ["load_tools"],
        "langchain_community.tools": ["WikipediaQueryRun"],
        "langchain_community.utilities": ["WikipediaAPIWrapper"],
        "langchain_core.tools": ["tool"],
        "_tools_test.logger": ["setup_logger"],
        "_tools_test.tools.basetool": ["execute_code", "execute_command", "list_directory"],
        "_tools_test.tools.FileEdit": ["collect_data", "create_document", "edit_document", "read_document"],
        "_tools_test.tools.internet": ["google_search", "scrape_webpages"],
    }
    for name, attributes in dependencies.items():
        module = ModuleType(name)
        for attribute in attributes:
            setattr(module, attribute, type("BaseTool", (), {}) if attribute == "BaseTool" else Mock())
        monkeypatch.setitem(sys.modules, name, module)
    real_monid = load_module("_tools_test.tools.monid", TOOLS / "monid.py")
    monkeypatch.setitem(sys.modules, "_tools_test.tools.monid", real_monid)
    factory = load_module("_tools_test.tools.factory", TOOLS / "factory.py").ToolFactory
    assert ("monid" in factory.list_available_tools()) == enabled
    assert factory.get_tool("scrape_webpages") is sys.modules[
        "_tools_test.tools.internet"
    ].scrape_webpages
    assert factory.list_available_tools()[:11] == [
        "execute_code", "execute_command", "list_directory", "create_document",
        "read_document", "edit_document", "collect_data", "google_search",
        "scrape_webpages", "wikipedia", "arxiv",
    ]


def test_missing_key_never_calls_http(monid, monkeypatch):
    monkeypatch.delenv("MONID_API_KEY")
    assert monid.monid(["https://example.com"]) == "Error: MONID_API_KEY is not set"
    monid.requests.post.assert_not_called()


def test_submission_http_error(monid):
    monid.requests.post.return_value.raise_for_status.side_effect = requests.HTTPError(
        "no balance"
    )
    assert monid.monid(["https://example.com"]) == "Error: no balance"
