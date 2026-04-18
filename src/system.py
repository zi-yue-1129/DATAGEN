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

    def run(self, user_input: str) -> None:
        graph = self.workflow_manager.get_graph()
        initial_state = create_initial_state(user_input)
        
        config_params = {"configurable": {"thread_id": "1"}, "recursion_limit": 3000}
        
        # Initialize the status spinner
        UI.show_spinner("正在初始化分析引擎...")
        
        try:
            stream = graph.stream(
                initial_state,
                config_params,
                stream_mode="values",
                debug=False
            )
            
            while True:
                try:
                    # Ensure status is running before we wait for the next event
                    UI.update_status("正在處理工作流...")
                    
                    event = next(stream, None)
                    if event is None:
                        break
                        
                    # Extract message
                    message = event["messages"][-1]
                    
                    # Update status message based on current active agent
                    last_agent = event.get("last_active_agent", "系統")
                    UI.update_status(f"正在執行: [bold magenta]{last_agent}[/bold magenta] ...")
                    
                    # Display the agent's message in a beautiful panel
                    if isinstance(message, AIMessage):
                        # Prefer name from message, then from state, then fallback
                        agent_display_name = getattr(message, "name", None) or last_agent or "Agent"
                        UI.print_agent_message(agent_display_name, message.content)
                    elif isinstance(message, HumanMessage):
                        UI.print_system_info(f"使用者輸入: {message.content}")
                    elif isinstance(message, tuple):
                        UI.print_system_info(str(message))
                        
                except KeyboardInterrupt:
                    # INTERVENTION: UI.stop_status() is called inside get_intervention_menu()
                    choice = get_intervention_menu()
                    
                    if choice == "繼續執行 (Continue)":
                        UI.print_system_info("恢復執行...")
                        continue
                    elif choice == "提供額外指令 (Add Instructions)":
                        new_instr = UI.ask_text("請輸入您的指令：")
                        if new_instr:
                            graph.update_state(config_params, {"messages": [HumanMessage(content=new_instr)]})
                            UI.print_system_info(f"已插入新指令: {new_instr}")
                        continue
                    elif choice == "查看當前狀態 (View State)":
                        UI.print_system_info("當前狀態摘要已顯示在日誌中 (或在此顯示面板)")
                        continue
                    elif choice == "結束研究 (Exit)":
                        UI.print_system_info("使用者選擇結束任務。")
                        raise
                    else:
                        continue
                except StopIteration:
                    break
                except Exception as e:
                    UI.print_error(f"工作流執行錯誤: {e}")
                    logger.exception("Workflow execution error")
                    break
        finally:
            UI.stop_status()

if __name__ == "__main__":
    system = MultiAgentSystem()
    user_input = UI.ask_text("Please enter your research topic: ")
    if user_input:
        system.run(user_input)