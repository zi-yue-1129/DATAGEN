import sys
import logging
import os
import warnings
import asyncio
import threading
import signal
from typing import Optional

# 1. Suppress the USER_AGENT warning
os.environ["USER_AGENT"] = "MultiAgentDataAnalysis/1.0"

# 2. Setup a stream interceptor to filter out unwanted prints
class OutputFilter:
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
    "FutureWarning"
])

from src.logger import setup_logger
from src.core.mcp_manager import get_mcp_manager
from src.utils.ui import UI

# Initialize the robust logger
logger = setup_logger()
warnings.filterwarnings("ignore")

from src.system import MultiAgentSystem

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

class ShutdownManager:
    """Manages formal shutdown and resource cleanup."""
    def __init__(self, mcp_loop, mcp_thread):
        self.mcp_loop = mcp_loop
        self.mcp_thread = mcp_thread
        self.is_shutting_down = False

    def shutdown(self):
        if self.is_shutting_down:
            return
        self.is_shutting_down = True
        UI.print_system_info("正在啟動正規關閉程序...")
        
        # Cleanup MCP loop
        if self.mcp_loop.is_running():
            UI.print_system_info("停止 MCP 背景事件迴圈...")
            self.mcp_loop.call_soon_threadsafe(self.mcp_loop.stop)
        
        self.mcp_thread.join(timeout=2)
        UI.print_header("系統已安全關閉。感謝使用！")
        sys.exit(0)

def run_mcp_loop(loop):
    """Run the background event loop for MCP connections."""
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except Exception as e:
        logger.error(f"MCP background loop error: {e}")

async def main():
    """Main async entry point"""
    UI.initialize()
    UI.print_header("Multi-Agent DataAnalysis System v3.0")
    
    # Initialize Multi-Agent System
    UI.update_status("正在初始化代理人系統...", agent="系統")
    system = MultiAgentSystem()
    
    UI.print_system_info("系統已準備就緒。輸入您的研究課題開始分析，或輸入 /help 查看命令。")

    while True:
        # Get input from the persistent resident input box
        user_input = await UI.get_input_async()
        
        if not user_input:
            continue
            
        if user_input.startswith("/"):
            # Handle Slash Commands
            cmd = user_input.lower()
            if cmd in ["/exit", "/quit", "/退出"]:
                UI.print_system_info("正在關閉系統...")
                break
            elif cmd == "/help":
                UI.print_system_info("可用命令: /exit, /help, /undo, /state")
                continue
            elif cmd == "/undo":
                UI.print_system_info("回退功能尚未實作。")
                continue
            elif cmd in ["/state", "/status"]:
                import platform
                from src.core.mcp_manager import get_mcp_manager
                manager = get_mcp_manager()
                servers = list(manager._connections.keys())
                status = f"\n  Python: {platform.python_version()}\n  OS: {platform.system()}\n  MCP 連線: {', '.join(servers) if servers else '無'}\n  工作目錄: {os.getcwd()}"
                UI.print_system_info(f"系統當前狀態: {status}")
                continue
            else:
                UI.print_error(f"未知命令: {cmd}")
                continue
        
        # Plain text - start or feed to the agent system
        UI.print_system_info(f"啟動任務: {user_input}")
        
        # Run the system in the background or await it
        # For simplicity, we await it here, but UI remains responsive during input pauses
        # To truly have dual-mode, we'd wrap system.run in a task
        try:
            await system.run(user_input)
        except Exception as e:
            UI.print_error(f"執行時發生錯誤: {e}")

    UI.print_header("系統已安全關閉。感謝使用！")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
