import sys
import logging
import os
import warnings
import asyncio
from typing import Optional

# 1. Suppress the USER_AGENT warning
os.environ["USER_AGENT"] = "MultiAgentDataAnalysis/1.0"

# 2. Setup a stream interceptor to filter out unwanted prints
class OutputFilter:
    """Filters unwanted stderr output."""
    def __init__(self, stream, blacklist):
        self.stream = stream
        self.blacklist = blacklist

    def write(self, data):
        if not any(term in data for term in self.blacklist):
            self.stream.write(data)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


sys.stderr = OutputFilter(sys.stderr, [
    "Secure MCP Filesystem Server",
    "Client does not support MCP Roots",
    "USER_AGENT environment variable not set",
    "FutureWarning",
])

from src.logger import setup_logger
from src.utils.ui import UI

logger = setup_logger()
warnings.filterwarnings("ignore")

from src.system import MultiAgentSystem

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


async def main() -> None:
    """Main async entry point."""
    # Initialize Claude-style bottom input bar
    UI.initialize()
    UI.print_header("Multi-Agent DataAnalysis System v3.0")

    UI.update_status("正在初始化代理人系統...", agent="系統")
    system = MultiAgentSystem()
    UI.print_system_info("系統已準備就緒。輸入您的研究課題開始分析，或輸入 /help 查看命令。")

    while True:
        # ── Claude-style bottom input bar (PromptSession) ───────────────────
        user_input = await UI.get_input_async()

        if not user_input:
            continue

        # ── Slash commands ──────────────────────────────────────────────────
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ["/exit", "/quit", "/退出"]:
                UI.print_system_info("正在關閉系統...")
                break
            elif cmd == "/help":
                UI.print_system_info("可用命令: /exit, /help, /undo, /state(/status)")
                continue
            elif cmd == "/undo":
                UI.print_system_info("回退功能尚未實作。")
                continue
            elif cmd in ["/state", "/status"]:
                import platform
                status = (
                    f"\n  Python: {platform.python_version()}"
                    f"\n  OS: {platform.system()}"
                    f"\n  工作目錄: {os.getcwd()}"
                )
                UI.print_system_info(f"系統當前狀態: {status}")
                continue
            else:
                UI.print_error(f"未知命令: {cmd}")
                continue

        UI.print_system_info(f"啟動任務: {user_input}")

        # ── KEY: Release PromptSession before running workflow ──────────────
        # questionary menus in executor threads need terminal control.
        # PromptSession holds terminal in raw mode via refresh_interval.
        # We destroy it first, let the workflow run, then rebuild it.
        UI.release_session()

        try:
            await system.run(user_input)
        except Exception as e:
            UI.print_error(f"執行時發生錯誤: {e}")
            logger.exception("Top-level run error")

        # ── Re-initialize PromptSession for next input ──────────────────────
        UI.initialize()

    UI.print_header("系統已安全關閉。感謝使用！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
