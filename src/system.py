import logging
from . import config
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from .core.workflow import WorkflowManager
from .core.language_models import LanguageModelManager
from .core.state import create_initial_state
from .logger import setup_logger
from .utils.ui import UI, get_intervention_menu

# Use the centralized logger
logger = setup_logger()

class MultiAgentSystem:
    def __init__(self):
        self.memory = MemorySaver()
        self.lm_manager = LanguageModelManager()
        self.workflow_manager = WorkflowManager(
            lm_manager=self.lm_manager,
            working_directory=config.WORKING_DIRECTORY
        )
        self.stop_requested = False

    async def run(self, user_input: str) -> None:
        graph = self.workflow_manager.get_graph()
        initial_state = create_initial_state(user_input)
        
        config_params = {"configurable": {"thread_id": "1"}, "recursion_limit": 3000}
        
        UI.show_spinner("正在初始化分析引擎...")
        
        try:
            current_node = None
            streamed_in_current_node = False
            
            # We use astream_events to capture both node transitions and chat model streaming
            async for event in graph.astream_events(
                initial_state,
                config_params,
                version="v2"
            ):
                if self.stop_requested:
                    break
                
                kind = event["event"]
                
                # Handle Status Updates (Node transitions)
                if kind == "on_chain_start" and event["name"] == "LangGraph":
                    UI.update_status("工作流已啟動", agent="系統")
                
                elif kind == "on_node_start":
                    node_name = event["name"]
                    current_node = node_name
                    streamed_in_current_node = False  # Reset for each node
                    UI.update_status(f"正在執行: [bold]{node_name}[/bold] ...", agent=node_name)
                
                # Handle Chat Model Streaming
                elif kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        streamed_in_current_node = True
                        # Update UI with incremental chunk via Live
                        UI.print_agent_message(current_node, content, is_stream=True)

                # Handle Final Messages from nodes
                elif kind == "on_node_end":
                    node_output = event["data"].get("output")
                    if node_output and "messages" in node_output:
                        last_msg = node_output["messages"][-1]
                        if isinstance(last_msg, AIMessage):
                            if streamed_in_current_node:
                                UI.end_stream()
                        elif isinstance(last_msg, HumanMessage):
                            UI.print_system_info(f"使用者輸入: {last_msg.content}")

            UI.update_status("任務完成", agent="系統")

        except Exception as e:
            UI.stop_status()
            UI.print_error(f"工作流執行錯誤: {e}")
            logger.exception("Workflow execution error")
        finally:
            UI.end_stream()
            UI.stop_status()

if __name__ == "__main__":
    import asyncio
    system = MultiAgentSystem()
    async def test():
        user_input = await UI.get_input_async("Please enter your research topic: ")
        if user_input:
            await system.run(user_input)
    asyncio.run(test())