"""Unit tests for src/utils/ui.py — PromptSession initialization kwargs.

Tests verify that UI.initialize() configures PromptSession with the correct
enhancements: FileHistory, AutoSuggestFromHistory, WordCompleter, and
multiline / key_bindings for Shift+Enter support.
"""
import pytest
from unittest.mock import patch
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from src.utils.ui import UI, _build_keybindings


@pytest.fixture(autouse=True)
def reset_ui():
    """Reset UI._session before/after each test to prevent cache pollution."""
    UI._session = None
    yield
    UI._session = None


# ── Task 1: FileHistory ────────────────────────────────────────────────────

def test_prompt_session_uses_file_history():
    """PromptSession must receive a FileHistory instance as `history`."""
    with patch("src.utils.ui.PromptSession") as mock_ps:
        UI.initialize()
        kwargs = mock_ps.call_args.kwargs
        assert "history" in kwargs, "PromptSession 未傳入 history 參數"
        assert isinstance(kwargs["history"], FileHistory), (
            f"history 應為 FileHistory，實際為 {type(kwargs['history'])}"
        )


# ── Task 2: AutoSuggestFromHistory ────────────────────────────────────────

def test_prompt_session_uses_auto_suggest():
    """PromptSession must receive an AutoSuggestFromHistory instance."""
    with patch("src.utils.ui.PromptSession") as mock_ps:
        UI.initialize()
        kwargs = mock_ps.call_args.kwargs
        assert "auto_suggest" in kwargs, "PromptSession 未傳入 auto_suggest 參數"
        assert isinstance(kwargs["auto_suggest"], AutoSuggestFromHistory), (
            f"auto_suggest 應為 AutoSuggestFromHistory，實際為 {type(kwargs['auto_suggest'])}"
        )


# ── Task 3: WordCompleter ─────────────────────────────────────────────────

def test_prompt_session_uses_word_completer_with_exit():
    """PromptSession must have a WordCompleter that includes '/exit'."""
    with patch("src.utils.ui.PromptSession") as mock_ps:
        UI.initialize()
        kwargs = mock_ps.call_args.kwargs
        assert "completer" in kwargs, "PromptSession 未傳入 completer 參數"
        completer = kwargs["completer"]
        assert isinstance(completer, WordCompleter), (
            f"completer 應為 WordCompleter，實際為 {type(completer)}"
        )
        assert "/exit" in completer.words, (
            f"/exit 不在補全清單中：{completer.words}"
        )


# ── Task 4: Multiline + KeyBindings ──────────────────────────────────────

def test_build_keybindings_has_newline_keys_and_enter():
    """_build_keybindings() must register newline keys and 'enter'."""
    kb = _build_keybindings()
    key_strs = [str(b.keys).lower() for b in kb.bindings]
    # Check for Control-J or (Escape, Enter) which are used for newlines
    has_newline = any("c-j" in k or "escape" in k for k in key_strs)
    # Control-M is the internal name for Enter
    has_enter = any("c-m" in k or "enter" in k for k in key_strs)
    assert has_newline, f"找不到換行鍵綁定 (c-j 或 escape, enter)，現有：{key_strs}"
    assert has_enter, f"找不到 enter 綁定，現有：{key_strs}"


def test_prompt_session_is_multiline_with_keybindings():
    """PromptSession must have multiline=True and a key_bindings object."""
    with patch("src.utils.ui.PromptSession") as mock_ps:
        UI.initialize()
        kwargs = mock_ps.call_args.kwargs
        assert kwargs.get("multiline") is True, (
            "PromptSession 應設定 multiline=True"
        )
        assert kwargs.get("key_bindings") is not None, (
            "PromptSession 應傳入 key_bindings"
        )
