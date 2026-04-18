import logging
from . import config
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from .core.workflow import WorkflowManager
from .core.language_models import LanguageModelManager
from .core.state import create_initial_state
from .logger import setup_logger

# Use the centralized logger
logger = setup_logger()

class MultiAgentSystem:
    def __init__(self):
        # Config is already loaded on import
        self.memory = MemorySaver()
        self.lm_manager = LanguageModelManager()
        self.workflow_manager = WorkflowManager(
            lm_manager=self.lm_manager,
            working_directory=config.WORKING_DIRECTORY
        )

    def run(self, user_input: str) -> None:
        graph = self.workflow_manager.get_graph()
        
        # Use factory function for consistent state initialization
        initial_state = create_initial_state(user_input)
        
        events = graph.stream(
            initial_state,
            {"configurable": {"thread_id": "1"}, "recursion_limit": 3000},
            stream_mode="values",
            debug=False
        )
        
        for event in events:
            message = event["messages"][-1]
            if isinstance(message, tuple):
                print(message, end='', flush=True)
            else:
                message.pretty_print()

if __name__ == "__main__":
    system = MultiAgentSystem()
    user_input = input("Please enter your research topic: ")
    system.run(user_input)