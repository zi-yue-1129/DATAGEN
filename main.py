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

def main():
    """Main entry point"""
    UI.print_header("Multi-Agent DataAnalysis System v2.0")
    
    # Create and start a background event loop for persistent MCP connections
    mcp_loop = asyncio.new_event_loop()
    mcp_thread = threading.Thread(target=run_mcp_loop, args=(mcp_loop,), daemon=True)
    mcp_thread.start()
    
    # Register the loop with the MCP manager
    manager = get_mcp_manager()
    manager._main_loop = mcp_loop
    
    shutdown_manager = ShutdownManager(mcp_loop, mcp_thread)

    # Signal handling for SIGTERM
    def handle_signal(signum, frame):
        shutdown_manager.shutdown()

    signal.signal(signal.SIGTERM, handle_signal)
    # Note: SIGINT (Ctrl+C) is handled via try/except in the main loop to support intervention

    try:
        system = MultiAgentSystem()
        
        # Interactive Topic Entry
        user_input = UI.ask_text("請輸入您的研究課題或分析需求：", 
                                default="datapath:OnlineSalesData.csv\nUse machine learning to perform data analysis and write reports")
        
        if not user_input or user_input.lower() in ['exit', 'quit', '退出']:
            shutdown_manager.shutdown()
            
        system.run(user_input)
        
        UI.print_system_info("研究任務已完成。")
        if UI.ask_choice("是否退出系統？", ["是", "否"]) == "是":
            shutdown_manager.shutdown()
            
    except KeyboardInterrupt:
        # This catch is mainly for cases outside the system.run intervention loop
        shutdown_manager.shutdown()
    except Exception as e:
        UI.print_error(f"系統運行時發生錯誤: {e}")
        logger.exception("Critical error in main loop")
    finally:
        shutdown_manager.shutdown()

if __name__ == "__main__":
    main()
