"""Tests for You.com web search, isolated from application startup."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "src" / "tools"
UA = "youdotcom-integration/zi-yue-1129-DATAGEN"


@pytest.fixture
def youcom(monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location(
        "_youcom_under_test", TOOLS / "youcom.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.requests, "get", Mock())
    monkeypatch.setattr(module.requests, "post", Mock())
    return module


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


PAYLOAD = {
    "results": {
        "web": [
            {
                "url": "https://example.com/a",
                "title": "A",
                "description": "desc a",
                "snippets": ["one", "two", "three"],
            },
            {"url": "https://example.com/b", "title": "B", "description": "desc b"},
        ],
        "news": [{"url": "https://example.com/n", "title": "N", "description": "news"}],
    }
}


def test_keyless_request_and_format(youcom):
    youcom.requests.get.return_value = response(PAYLOAD)
    out = youcom.youcom_search("datagen", count=5)
    assert out == (
        "A\none two\nhttps://example.com/a\n\n"
        "B\ndesc b\nhttps://example.com/b\n\n"
        "N\nnews\nhttps://example.com/n\n\n"
    )
    args, kwargs = youcom.requests.get.call_args
    assert args == ("https://api.you.com/v1/agents/search",)
    assert kwargs["params"] == {"query": "datagen", "count": 5}
    assert kwargs["headers"]["User-Agent"] == UA
    assert "X-API-Key" not in kwargs["headers"]
    youcom.requests.post.assert_not_called()


def test_keyless_count_capped_at_50(youcom):
    youcom.requests.get.return_value = response({"results": {"web": []}})
    assert youcom.youcom_search("q", count=500) == ""
    assert youcom.requests.get.call_args.kwargs["params"]["count"] == 50


def test_keyed_request(youcom, monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    youcom.requests.post.return_value = response(PAYLOAD)
    youcom.youcom_search("q", count=150)
    args, kwargs = youcom.requests.post.call_args
    assert args == ("https://ydc-index.io/v1/search",)
    assert kwargs["json"] == {"query": "q", "count": 100}
    assert kwargs["headers"]["X-API-Key"] == "test-key"
    assert kwargs["headers"]["User-Agent"] == UA
    youcom.requests.get.assert_not_called()


def test_rejected_key(youcom, monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "bad")
    youcom.requests.post.return_value = response({}, status=401)
    with pytest.raises(ValueError, match="rejected YDC_API_KEY"):
        youcom.youcom_search("q")


@pytest.mark.parametrize("status", [402, 429])
def test_keyless_limit_points_at_key(youcom, status):
    youcom.requests.get.return_value = response({}, status=status)
    with pytest.raises(ValueError, match="Set YDC_API_KEY"):
        youcom.youcom_search("q")


@pytest.fixture
def internet(monkeypatch):
    module = pytest.importorskip("src.tools.internet")
    monkeypatch.setattr(module, "youcom_search", Mock(return_value="R\ns\nu\n\n"))
    return module


def test_google_search_falls_back_when_selenium_fails(internet, monkeypatch):
    monkeypatch.setattr(internet, "SEARCH_PROVIDER", "google")
    monkeypatch.setattr(
        internet.webdriver, "Chrome", Mock(side_effect=RuntimeError("no driver"))
    )
    assert internet.google_search.invoke({"query": "q"}) == "R\ns\nu\n\n"
    internet.youcom_search.assert_called_once_with("q", count=5)


def test_search_provider_youcom_skips_selenium(internet, monkeypatch):
    monkeypatch.setattr(internet, "SEARCH_PROVIDER", "youcom")
    chrome = Mock()
    monkeypatch.setattr(internet.webdriver, "Chrome", chrome)
    assert internet.google_search.invoke({"query": "q"}) == "R\ns\nu\n\n"
    chrome.assert_not_called()


def test_fallback_error_is_returned_as_text(internet, monkeypatch):
    monkeypatch.setattr(internet, "SEARCH_PROVIDER", "youcom")
    internet.youcom_search.side_effect = ValueError("limit")
    assert internet.google_search.invoke({"query": "q"}) == "Error: limit"


def test_mcp_adapter_drops_unset_optional_arguments(monkeypatch):
    mcp_tools = pytest.importorskip("src.tools.mcp_tools")
    manager = Mock()

    async def call_tool(server, name, arguments):
        manager.calls.append((server, name, arguments))
        return "ok"

    manager.calls = []
    manager.call_tool = call_tool
    import src.core.mcp_manager as mcp_manager

    monkeypatch.setattr(mcp_manager, "get_mcp_manager", lambda: manager)
    tool = mcp_tools.create_mcp_tool_adapter(
        "you-search",
        "Search",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer"},
                "freshness": {"type": "string"},
            },
            "required": ["query"],
        },
        "web-search",
    )
    import asyncio

    assert asyncio.run(tool.ainvoke({"query": "q", "count": 2})) == "ok"
    assert manager.calls == [("web-search", "you-search", {"query": "q", "count": 2})]
