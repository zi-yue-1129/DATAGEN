import logging
import sys

class SilenceFilter(logging.Filter):
    """Filter out noisy messages that we don't want to see in the console."""
    def filter(self, record):
        msg = record.getMessage()
        # Blacklist of noisy substrings
        blacklist = [
            "asynchronous generator",
            "cancel scope",
            "different task than it was entered in",
            "Loaded",
            "tools from MCP",
            "Created adapter",
            "Connected to MCP",
            "Connecting to MCP",
            "Discovered",
            "Client does not support MCP Roots",
            "Traceback",
            "GeneratorExit"
        ]
        return not any(term in msg for term in blacklist)

# Configure logging
def setup_logger(log_file:str='agent.log'):
    # Clear root logger handlers to prevent duplicates from other modules
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)

    logger = logging.getLogger("src") # Use a top-level name
    logger.setLevel(logging.DEBUG)
    logger.propagate = False # Prevent double logging

    if logger.hasHandlers():
        logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler (Keep everything for debugging)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler (Filtered progress)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Force global suppression again to be sure
    for name in ["asyncio", "anyio", "httpx", "httpcore", "langchain", "langgraph"]:
        logging.getLogger(name).setLevel(logging.CRITICAL)
    
    return logger
