import sys
import logging
import os
import warnings
import asyncio
import threading

# 1. Suppress the USER_AGENT warning
os.environ["USER_AGENT"] = "MultiAgentDataAnalysis/1.0"

# 2. Setup a stream interceptor to filter out unwanted prints from libraries/subprocesses
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

# Apply filter to stderr where most MCP server noise lives
sys.stderr = OutputFilter(sys.stderr, [
    "Secure MCP Filesystem Server",
    "Client does not support MCP Roots",
    "USER_AGENT environment variable not set",
    "FutureWarning"
])

from src.logger import setup_logger
from src.core.mcp_manager import get_mcp_manager

# Initialize the robust logger first thing
logger = setup_logger()
warnings.filterwarnings("ignore")

from src.system import MultiAgentSystem

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def run_mcp_loop(loop):
    """Run the background event loop for MCP connections."""
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except Exception as e:
        logger.error(f"MCP background loop error: {e}")

def main():
    """Main entry point"""
    # Create and start a background event loop for persistent MCP connections
    mcp_loop = asyncio.new_event_loop()
    mcp_thread = threading.Thread(target=run_mcp_loop, args=(mcp_loop,), daemon=True)
    mcp_thread.start()
    
    # Register the loop with the MCP manager
    manager = get_mcp_manager()
    manager._main_loop = mcp_loop
    
    try:
        system = MultiAgentSystem()
        
        # Example usage
        user_input = '''
        datapath:OnlineSalesData.csv
        Use machine learning to perform data analysis and write complete graphical reports
        '''
        system.run(user_input)
    finally:
        # Cleanup
        if mcp_loop.is_running():
            mcp_loop.call_soon_threadsafe(mcp_loop.stop)
        mcp_thread.join(timeout=2)

if __name__ == "__main__":
    main()
