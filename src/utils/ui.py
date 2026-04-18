from __future__ import annotations
import sys
import asyncio
from typing import Any, Optional, List
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.theme import Theme
from rich import box

import questionary

# Define a professional color palette as requested
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

# Use force_terminal=True to ensure colors work in SSH/VSCode
console = Console(theme=AGENT_THEME, force_terminal=True)

class UI:
    """Centralized UI components for the Multi-agent system (Original Style)."""
    _active_status: Optional[Any] = None
    
    @staticmethod
    def initialize():
        """No-op for backward compatibility."""
        pass

    @staticmethod
    def print_header(title: str):
        UI.stop_status()
        console.print("\n")
        console.print(Panel(
            f"[bold cyan]{title.upper()}[/bold cyan]", 
            expand=True, 
            border_style="bold cyan",
            box=box.DOUBLE,
            padding=(1, 4)
        ))
        console.print("\n")

    @staticmethod
    def print_agent_message(agent_name: str, content: str, is_stream: bool = False):
        """Print agent message with Markdown support (Original Style)."""
        UI.stop_status()
        
        # Handle streaming differently in original style
        if is_stream:
            # For streaming, we just output raw text to console
            # Markdown rendering will happen in the final full message
            console.print(content, end="")
            return

        prefix = agent_name.split('_')[0].lower()
        style_key = f"agent.{prefix}"
        
        # Check if style exists, otherwise fallback to info
        try:
            console.get_style(style_key)
        except Exception:
            style_key = "info"
            
        md = Markdown(content, code_theme="monokai", inline_code_lexer="python")
        
        # Enhanced Panel with rounded corners and padding, no emojis
        panel = Panel(
            md,
            title=f"[bold]{agent_name.upper()}[/bold]",
            title_align="left",
            border_style=style_key,
            padding=(1, 2),
            subtitle=f"[dim]SYSTEM AGENT NODE[/dim]",
            subtitle_align="right"
        )
        console.print(panel)

    @staticmethod
    def end_stream():
        """Simply add a newline for original style."""
        console.print("\n")

    @staticmethod
    def print_system_info(message: str):
        UI.stop_status()
        console.print(f"[info]ℹ {message}[/info]")

    @staticmethod
    def print_warning(message: str):
        UI.stop_status()
        console.print(f"[warning]⚠ {message}[/warning]")

    @staticmethod
    def print_error(message: str):
        UI.stop_status()
        console.print(f"[error]✘ {message}[/error]")

    @staticmethod
    async def get_input_async(prompt: str = ">>> ") -> str:
        """Async input using questionary to maintain the original look."""
        UI.stop_status()
        try:
            result = await questionary.text(prompt).ask_async()
            return (result or "").strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    @staticmethod
    def ask_choice(message: str, choices: list[str]) -> str:
        """Sync choice prompt using questionary."""
        UI.stop_status()
        res = questionary.select(message, choices=choices).ask()
        return res if res else "/exit"

    @staticmethod
    async def ask_choice_async(message: str, choices: list[str]) -> str:
        """Async choice prompt using questionary."""
        UI.stop_status()
        res = await questionary.select(message, choices=choices).ask_async()
        return res if res else "/exit"

    @staticmethod
    def ask_text(message: str, default: str = "") -> str:
        UI.stop_status()
        return questionary.text(message, default=default).ask()

    @staticmethod
    def show_spinner(message: str):
        UI.stop_status()
        UI._active_status = console.status(f"[info]{message}[/info]", spinner="dots")
        UI._active_status.start()
        return UI._active_status

    @staticmethod
    def stop_status():
        if UI._active_status:
            try:
                UI._active_status.stop()
                UI._active_status = None
            except Exception:
                pass

    @staticmethod
    def update_status(message: str, agent: Optional[str] = None):
        """Update existing spinner or create new one."""
        if not UI._active_status:
            UI.show_spinner(message)
        else:
            UI._active_status.update(f"[info]{message}[/info]")

def get_intervention_menu() -> str:
    """Display the intervention menu and return the user's choice."""
    UI.stop_status()
    console.print("\n[human] ⏸ 工作流已暫停 [/human]")
    # Use sync ask because it's usually called from nodes
    res = questionary.select(
        "您想要做什麼？",
        choices=[
            "繼續執行 (Continue)",
            "提供額外指令 (Add Instructions)",
            "查看當前狀態 (View State)",
            "結束研究 (Exit)"
        ]
    ).ask()
    return res if res else "結束研究 (Exit)"
