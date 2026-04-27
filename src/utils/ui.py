from __future__ import annotations
import sys
from typing import Optional, List, Any
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.theme import Theme
from rich import box
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
import os
import questionary

# Professional color palette
AGENT_THEME = Theme({
    "info": "dim cyan",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "agent.hypothesis": "bold orchid",
    "agent.note": "bold sky_blue1",
    "agent.process": "bold spring_green3",
    "agent.viz": "bold orange1",
    "agent.quality": "bold gold1",
    "agent.code": "bold chartreuse3",
    "agent.search": "bold steel_blue1",
    "agent.report": "bold slate_blue1",
    "agent.refiner": "bold deep_pink3",
    "human": "bold white on purple",
})

console = Console(theme=AGENT_THEME, force_terminal=True)

# Persistent history file path
_HISTORY_FILE = os.path.expanduser("~/.multi_agent_da_history")

# Slash commands available for tab-completion
_COMMANDS = ["/exit", "/help", "/reset"]

# Claude Code style for the bottom input bar
_PROMPT_STYLE = Style.from_dict({
    "bottom-toolbar": "bg:#1e1e1e #555555",
    "bottom-toolbar.text": "fg:#00cccc",
    "prompt": "fg:#ffffff bold",
})


def _build_keybindings() -> KeyBindings:
    """Build custom key bindings: Enter submits, Ctrl-J or Alt-Enter inserts newline.

    Returns:
        A KeyBindings instance with submission and newline keys configured.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _(event) -> None:  # noqa: ANN001
        # Enter submits immediately (overrides multiline default of inserting newline)
        event.current_buffer.validate_and_handle()

    @kb.add("c-j")
    @kb.add("escape", "enter")
    def _(event) -> None:  # noqa: ANN001
        # Control-J or Alt+Enter inserts a newline
        event.current_buffer.insert_text("\n")

    return kb

# Style map for agent name → theme key
_STYLE_MAP = {
    "hypothesis": "agent.hypothesis",
    "note":       "agent.note",
    "process":    "agent.process",
    "viz":        "agent.viz",
    "quality":    "agent.quality",
    "code":       "agent.code",
    "search":     "agent.search",
    "report":     "agent.report",
    "refiner":    "agent.refiner",
}

def _get_style(agent_name: str) -> str:
    """Resolve agent name prefix → theme style key."""
    if not agent_name:
        return "info"
    prefix = agent_name.split("_")[0].lower()
    return _STYLE_MAP.get(prefix, "info")


class UI:
    """
    Architecture:
    - Main input   → PromptSession (bottom toolbar, Claude style)
    - Node menus   → questionary   (arrow-key selectable)
    - Agent output → Rich Panel    (Markdown rendered)
    - While gen.   → Rich spinner  (status indicator)

    PromptSession & questionary are NEVER active at the same time,
    so there is no terminal control conflict.
    """

    _status: Optional[Any] = None      # rich status context
    _session: Optional[PromptSession] = None
    _current_agent: str = "系統"
    _current_status_msg: str = "就緒"
    _stream_buffer: str = ""             # accumulated streaming content
    _stream_agent: str = ""              # agent name for the current stream
    _live: Optional[Live] = None         # Live renderer for streaming

    # ── Init ────────────────────────────────────────────────────────────────

    @staticmethod
    def initialize() -> None:
        """Initialize the PromptSession with Claude Code-style UX enhancements.

        Features added:
            - FileHistory: persistent cross-session input history.
            - AutoSuggestFromHistory: grey-text inline suggestion.
            - WordCompleter: Tab-completion for slash commands.
            - multiline + KeyBindings: Alt+Enter or Ctrl-J for newline, Enter to submit.

        Note: Terminal UI does not natively render LaTeX math blocks; they will appear as raw text.
        """
        if UI._session is None:
            UI._session = PromptSession(
                style=_PROMPT_STYLE,
                history=FileHistory(_HISTORY_FILE),
                auto_suggest=AutoSuggestFromHistory(),
                completer=WordCompleter(_COMMANDS, sentence=True),
                key_bindings=_build_keybindings(),
                multiline=True,
            )

    @staticmethod
    def release_session() -> None:
        """Destroy the PromptSession so questionary can take terminal control."""
        UI._session = None

    # ── Header ──────────────────────────────────────────────────────────────

    @staticmethod
    def print_header(title: str) -> None:
        console.print("\n")
        console.print(Panel(
            f"[bold cyan]{title.upper()}[/bold cyan]",
            expand=True,
            border_style="bold cyan",
            box=box.DOUBLE,
            padding=(1, 4),
        ))
        console.print("\n")

    # ── Agent Messages ───────────────────────────────────────────────────────

    @staticmethod
    def _make_panel(agent_name: str, content: str) -> Panel:
        """Build a Markdown Panel for a given agent and content."""
        style_key = _get_style(agent_name)
        safe_name = (agent_name or "AGENT").upper()
        return Panel(
            Markdown(content),
            title=f"[bold]{safe_name}[/bold]",
            title_align="left",
            border_style=style_key,
            padding=(1, 2),
            subtitle="[dim]DataAnalysis Agent Node[/dim]",
            subtitle_align="right",
            box=box.ROUNDED,
        )

    @staticmethod
    def _flush_live() -> None:
        """Stop Live — final frame stays on screen, no erase/reprint cycle."""
        if UI._live is not None:
            try:
                UI._live.refresh()
            except Exception:
                pass
            UI._live.stop()
            UI._live = None
        UI._stream_buffer = ""
        UI._stream_agent = ""

    @staticmethod
    def print_agent_message(
        agent_name: str, content: str, is_stream: bool = False
    ) -> None:
        """
        is_stream=True  → Real-time Markdown rendering via rich.live.Live
        is_stream=False → Flush any live stream, then render static Panel
        """
        safe_name = agent_name or "AGENT"

        if is_stream:
            # Name Stability: prioritize specific names over generic "AGENT"
            if safe_name == "AGENT" and UI._stream_agent and UI._stream_agent != "AGENT":
                safe_name = UI._stream_agent

            # If agent changed, flush current stream
            if UI._live is not None and UI._stream_agent and UI._stream_agent != safe_name:
                UI._flush_live()

            UI._stream_agent = safe_name
            UI.stop_status()

            if not content:
                return

            UI._stream_buffer += content
            panel = UI._make_panel(safe_name, UI._stream_buffer)

            if UI._live is None:
                UI._live = Live(
                    panel,
                    console=console,
                    auto_refresh=False,
                    vertical_overflow="visible",
                )
                UI._live.start()
            else:
                UI._live.update(panel)
            UI._live.refresh()
            return

        # Static output
        UI.stop_status()
        UI._flush_live()

        if content.strip():
            console.print(UI._make_panel(safe_name, content))

    @staticmethod
    def end_stream() -> None:
        """Stop Live and commit the final Markdown Panel."""
        UI._flush_live()

    # ── Spinner / Status ─────────────────────────────────────────────────────

    @staticmethod
    def show_spinner(message: str) -> None:
        # Skip if Live stream is already active (two Lives cannot coexist)
        if UI._live is not None:
            return
        UI.stop_status()
        UI._current_status_msg = message
        UI._status = console.status(f"[info]{message}[/info]", spinner="dots")
        UI._status.start()

    @staticmethod
    def update_status(message: str, agent: Optional[str] = None) -> None:
        UI._current_status_msg = message
        if agent:
            UI._current_agent = agent
        # Skip spinner management if Live is already rendering
        if UI._live is not None:
            return
        if UI._status is None:
            UI.show_spinner(message)
        else:
            UI._status.update(f"[info]{message}[/info]")

    @staticmethod
    def stop_status() -> None:
        if UI._status is not None:
            UI._status.stop()
            UI._status = None

    # ── Info Prints ──────────────────────────────────────────────────────────

    @staticmethod
    def print_system_info(message: str) -> None:
        UI.stop_status()
        console.print(f"[info]ℹ {message}[/info]")

    @staticmethod
    def print_warning(message: str) -> None:
        UI.stop_status()
        console.print(f"[warning]⚠ {message}[/warning]")

    @staticmethod
    def print_error(message: str) -> None:
        UI.stop_status()
        console.print(f"[error]✘ {message}[/error]")

    # ── Input (PromptSession — main loop only) ───────────────────────────────

    @staticmethod
    async def get_input_async(prompt: str = "> ") -> str:
        """
        Claude Code style bottom input with persistent toolbar.
        Called ONLY from the main async loop (never from node threads).
        """
        UI._flush_live()  # Ensure any active stream is committed and Live stopped
        UI.stop_status()
        UI.initialize()

        def _toolbar():
            return HTML(
                f'<style bg="#1e1e1e" fg="#00cccc"> ⬡ Agent: {UI._current_agent} </style>'
                f'<style bg="#1e1e1e" fg="#888888"> │ {UI._current_status_msg} </style>'
            )

        try:
            result = await UI._session.prompt_async(
                HTML(f"<b>{prompt}</b>"),
                bottom_toolbar=_toolbar,
                refresh_interval=0.5,
            )
            return (result or "").strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    # ── Menus (questionary — node threads) ──────────────────────────────────

    @staticmethod
    def ask_choice(message: str, choices: List[str]) -> str:
        """Arrow-key selectable menu. Flushes Live stream first."""
        UI._flush_live()   # commit streamed panel before taking terminal
        UI.stop_status()
        res = questionary.select(message, choices=choices).ask()
        return res if res else "/exit"

    @staticmethod
    async def ask_choice_async(message: str, choices: List[str]) -> str:
        UI._flush_live()
        UI.stop_status()
        res = await questionary.select(message, choices=choices).ask_async()
        return res if res else "/exit"

    @staticmethod
    def ask_text(message: str, default: str = "") -> str:
        """Single-line text input. Flushes Live stream first."""
        UI._flush_live()
        UI.stop_status()
        res = questionary.text(message, default=default).ask()
        return (res or default).strip()

    @staticmethod
    async def ask_text_async(message: str, default: str = "") -> str:
        UI._flush_live()
        UI.stop_status()
        res = await questionary.text(message, default=default).ask_async()
        return (res or default).strip()



# ── Intervention Menu ────────────────────────────────────────────────────────

def get_intervention_menu() -> str:
    """Pause menu — arrow-key selectable."""
    UI.stop_status()
    console.print("\n[human] ⏸ 工作流已暫停 [/human]")
    res = questionary.select(
        "您想要做什麼？",
        choices=[
            "繼續執行 (Continue)",
            "提供額外指令 (Add Instructions)",
            "結束研究 (Exit)",
        ],
    ).ask()
    return res if res else "結束研究 (Exit)"
