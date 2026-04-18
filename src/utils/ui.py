from __future__ import annotations
import sys
from typing import Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.theme import Theme
from rich import box
import questionary

# Define a professional color palette
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

console = Console(theme=AGENT_THEME)

class UI:
    """Centralized UI components for the Multi-agent system."""
    _active_status: Optional[Any] = None
    
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
    def print_agent_message(agent_name: str, content: str):
        UI.stop_status()
        
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
    def print_system_info(message: str):
        UI.stop_status()
        console.print(f"[info]ℹ {message}[/info]")

    @staticmethod
    def print_error(message: str):
        UI.stop_status()
        console.print(f"[error]✘ {message}[/error]")

    @staticmethod
    def ask_choice(message: str, choices: list[str]) -> str:
        UI.stop_status()
        return questionary.select(message, choices=choices).ask()

    @staticmethod
    def ask_text(message: str, default: str = "") -> str:
        UI.stop_status()
        return questionary.text(message, default=default).ask()

    @staticmethod
    def show_spinner(message: str):
        UI._active_status = console.status(f"[info]{message}[/info]", spinner="dots")
        return UI._active_status

    @staticmethod
    def stop_status():
        if UI._active_status:
            try:
                UI._active_status.stop()
            except Exception:
                pass

    @staticmethod
    def update_status(message: str):
        if UI._active_status:
            UI._active_status.update(f"[info]{message}[/info]")
            try:
                UI._active_status.start()
            except Exception:
                pass

def get_intervention_menu() -> str:
    """Display the intervention menu and return the user's choice."""
    UI.stop_status()
    console.print("\n[human] ⏸ 工作流已暫停 [/human]")
    return questionary.select(
        "您想要做什麼？",
        choices=[
            "繼續執行 (Continue)",
            "提供額外指令 (Add Instructions)",
            "查看當前狀態 (View State)",
            "回退上一步 (Undo - Not implemented)",
            "結束研究 (Exit)"
        ]
    ).ask()
