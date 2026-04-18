from __future__ import annotations
from typing import Any, Union, TYPE_CHECKING
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
import logging
import json
import re
from pathlib import Path
import time

from .state import State
from ..config import WORKING_DIRECTORY
from ..utils.ui import UI

if TYPE_CHECKING:
    from .state import State
    from ..agents.base import BaseAgent

# Set up logger
logger = logging.getLogger(__name__)

def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
    """Helper to safely get attributes from State whether it's Pydantic or dict."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)

def update_artifact_dict(current_artifacts: dict[str, str], new_output: dict[str, str] | str | Any) -> dict[str, str]:
    """
    Update an artifact dictionary with new output.
    If output is a string (legacy), wrap it. 
    If output is a dict, update.
    """
    updated = current_artifacts.copy() if current_artifacts else {}
    
    if isinstance(new_output, dict):
        updated.update(new_output)
    elif isinstance(new_output, str) and new_output:
        # Legacy/Fallback: Generate a timestamped key for raw string output
        # This ensures we don't lose data even if agents aren't fully migrated
        timestamp = int(time.time())
        key = f"output_{timestamp}.txt"
        summary = new_output[:100] + "..." if len(new_output) > 100 else new_output
        updated[key] = summary
    
    return updated


def safe_get_content(output: Any, keys: list[str], default: str = "") -> str:
    """Safely extract content from output (Pydantic, dict, or str)."""
    if isinstance(output, str) and output.strip():
        return output
    
    # Check for common reasoning/content keys
    all_keys = keys + ["thought", "reasoning", "analysis", "reflection", "response", "answer"]
    
    if isinstance(output, dict):
        for key in all_keys:
            if key in output and output[key]:
                return str(output[key])
        return str(output) if output else default
    
    for key in all_keys:
        if hasattr(output, key):
            val = getattr(output, key, None)
            if val:
                return str(val)
    
    return str(output) if output else default

def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract and parse JSON from text, handling markdown blocks."""
    if not text:
        return None
        
    # Try markdown block first
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
            
    # Try finding the first '{' and last '}'
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1:
        try:
            return json.loads(text[start_idx:end_idx+1])
        except json.JSONDecodeError:
            pass
            
    return None

def get_structured_output(result: Any, agent: BaseAgent) -> Any:
    """Extract structured output from agent result, with fallback parsing."""
    # 1. Direct structured response in result dict
    if isinstance(result, dict) and "structured_response" in result:
        return result["structured_response"]
        
    # 2. Result itself might be the structured object (Pydantic)
    if hasattr(result, "dict") or hasattr(result, "model_dump"):
        return result
        
    # 3. Last message content might be a JSON string
    content = ""
    if isinstance(result, dict) and "messages" in result and result["messages"]:
        content = result["messages"][-1].content
    elif hasattr(result, "content"):
        content = result.content
    elif isinstance(result, str):
        content = result
        
    if content:
        parsed = extract_json_from_text(content)
        if parsed:
            return parsed
            
    return None

def agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """Process an agent's action and update the state accordingly."""
    logger.debug(f"Processing agent: {name}")
    try:
        result = agent.invoke(state)
        
        # Robust structured output extraction
        output = get_structured_output(result, agent)
        
        # Extract content for AI message
        if output:
            content = safe_get_content(output, ["task", "feedback", "summary", "current_instruction", "hypothesis"])
            ai_message = AIMessage(content=content, name=name)
        else:
            # Fallback to last message or raw result
            if isinstance(result, dict) and "messages" in result and result["messages"]:
                last_msg = result["messages"][-1]
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    # Provide visual feedback for tool-using agents
                    tool_names = [tc['name'] for tc in last_msg.tool_calls]
                    content = f"*CALLING TOOLS:* {', '.join(tool_names)}"
                else:
                    content = last_msg.content or f"*(代理人 {name} 已完成任務)*"
                ai_message = AIMessage(content=content, name=name)
            else:
                content = str(result) if result else f"*(代理人 {name} 無返回內容)*"
                ai_message = AIMessage(content=content, name=name)

        # Base Updates
        current_messages = list(get_state_attr(state, "messages", []))
        updates = {
            "messages": current_messages + [ai_message],
            "last_active_agent": name
        }

        # StateUpdater Protocol
        if hasattr(agent, "get_state_updates"):
            agent_updates = agent.get_state_updates(state, output)
            if agent_updates:
                updates.update(agent_updates)
        
        # Increment workflow step counter
        current_step = get_state_attr(state, "step_count", 0)
        updates["step_count"] = current_step + 1
        
        # Track completed tasks for workflow progress monitoring
        current_instruction = get_state_attr(state, "current_instruction", None)
        if current_instruction:
            completed = list(get_state_attr(state, "completed_tasks", []))
            if current_instruction not in completed:
                completed.append(current_instruction)
                updates["completed_tasks"] = completed
        
        return updates
        
    except Exception as e:
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {
            "messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name=name)],
            "last_active_agent": name
        }

def human_choice_node(state: State) -> dict[str, Any]:
    """Handle human input to choose the next step."""
    choice_map = {
        "重新生成假設 (Regenerate hypothesis)": "1",
        "繼續研究流程 (Continue research process)": "2"
    }
    
    choice_text = UI.ask_choice("請選擇下一步：", list(choice_map.keys()))
    if not choice_text:
        # Default fallback if user cancels (Esc)
        choice = "2"
    else:
        choice = choice_map[choice_text]
    
    current_messages = list(get_state_attr(state, "messages", []))
    updates = {
        "messages": current_messages,
        "last_active_agent": "human"
    }
    
    if choice == "1":
        modification_areas = UI.ask_text("請指定需要修改的領域：")
        updates["messages"] = current_messages + [HumanMessage(content=f"Regenerate hypothesis. Areas: {modification_areas}")]
        updates["hypothesis"] = None  # Clear hypothesis
    else:
        updates["messages"] = current_messages + [HumanMessage(content="Continue the research process")]
        updates["current_instruction"] = "Continue the research process"
    
    return updates

def create_message(message: Any, name: str) -> BaseMessage:
    """Create a BaseMessage object based on the message type."""
    if isinstance(message, dict):
        content = message.get("content", "")
        message_type = str(message.get("type", "ai")).lower()
    else:
        content = getattr(message, "content", str(message))
        message_type = str(getattr(message, "type", "ai")).lower()
        
    return HumanMessage(content=content) if message_type == "human" else AIMessage(content=content, name=name)

def note_agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """Process the note agent's action and update the entire state."""
    logger.info(f"Processing note agent: {name}")
    try:
        current_messages = list(get_state_attr(state, "messages", []))
        
        # Context window management
        head_messages: list[BaseMessage] = []
        tail_messages: list[BaseMessage] = []
        processing_messages = current_messages
        
        if len(current_messages) > 6:
            head_messages = list(current_messages[:2]) 
            tail_messages = list(current_messages[-2:])
            # Create a localized state for the agent with trimmed messages
            # Note: We need to pass a dict-like object if agent expects it
            processing_messages = list(current_messages[2:-2])
            logger.debug("Trimmed messages for processing")
        
        # Prepare state for invocation (cast to dict if needed for compatibility)
        invoke_state = state.dict() if hasattr(state, "dict") else dict(state)
        invoke_state["messages"] = processing_messages
        
        result = agent.invoke(invoke_state)
        output = get_structured_output(result, agent)
        
        if not output:
            logger.error(f"Note agent {name} failed to return structured response. Result: {str(result)[:500]}")
            # Try to use raw message if available
            raw_content = ""
            if isinstance(result, dict) and "messages" in result and result["messages"]:
                raw_content = result["messages"][-1].content
            elif hasattr(result, "content"):
                raw_content = result.content
            
            return _create_error_state(state, AIMessage(content=f"Error: Agent {name} failed to return structured response. Raw: {raw_content[:200]}", name=name), name, "Missing structured response")

        # Map NoteState output fields to New State Schema
        # Use helper for safe attribute access
        def safe_get(obj, key, default=""):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        new_messages_data = safe_get(output, "messages", [])
        new_messages = [create_message(msg, name) for msg in new_messages_data] if isinstance(new_messages_data, list) else []
        messages: list[BaseMessage] = list(new_messages) if new_messages else list(processing_messages)
        combined_messages = head_messages + messages + tail_messages
        
        updated_state = {
            "messages": combined_messages,
            "hypothesis": str(safe_get(output, "hypothesis", "")),
            
            # Semantic Mapping
            "current_instruction": str(safe_get(output, "current_instruction", safe_get(output, "process", ""))),
            "next_workflow_step": str(safe_get(output, "next_workflow_step", safe_get(output, "process_decision", ""))),
            
            # Artifact Mapping
            "search_artifacts": update_artifact_dict({}, str(safe_get(output, "search_artifacts", safe_get(output, "searcher_state", "")))),
            "data_viz_artifacts": update_artifact_dict({}, str(safe_get(output, "data_viz_artifacts", safe_get(output, "visualization_state", "")))),
            "code_artifacts": update_artifact_dict({}, str(safe_get(output, "code_artifacts", safe_get(output, "code_state", "")))),
            "report_artifacts": update_artifact_dict({}, str(safe_get(output, "report_artifacts", safe_get(output, "report_section", "")))),
            
            "quality_feedback": str(safe_get(output, "quality_feedback", safe_get(output, "quality_review", ""))),
            "needs_revision": bool(safe_get(output, "needs_revision", False)),
            
            "last_active_agent": 'note_agent'
        }
        
        return updated_state

    except Exception as e:
        logger.error(f"Unexpected error in note_agent_node: {e}", exc_info=True)
        return _create_error_state(state, AIMessage(content=f"Unexpected error: {str(e)}", name=name), name, "Unexpected error")

def _create_error_state(state: State, error_message: AIMessage, name: str, error_type: str) -> dict[str, Any]:
    """Create an error state when an exception occurs."""
    logger.info(f"Creating error state for {name}: {error_type}")
    
    # Base on current state
    current_dict = state.dict() if hasattr(state, "dict") else dict(state)
    
    current_dict["messages"] = list(get_state_attr(state, "messages", [])) + [error_message]
    current_dict["last_active_agent"] = name
    
    return current_dict

def human_review_node(state: State) -> dict[str, Any]:
    """Display current state and handle user interaction."""
    try:
        UI.print_system_info("當前研究進度摘要已顯示。")
        
        needs_more = UI.ask_choice("您是否需要額外的分析或修改？", ["是 (Yes)", "否 (No)"]) == "是 (Yes)"
        
        updates: dict[str, Any] = {"last_active_agent": "human"}
        
        if needs_more:
            req = UI.ask_text("請輸入您的需求：")
            if req:
                updates["messages"] = [HumanMessage(content=req)]
                updates["needs_revision"] = True
        else:
            updates["needs_revision"] = False
            updates["revision_count"] = 0
        
        return updates
        
    except Exception as e:
        logger.error(f"Error in human_review: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {"messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name="human_review")]}

def refiner_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """Process report materials with refiner agent."""
    try:
        storage_path = Path(WORKING_DIRECTORY)
        materials = []
        
        # Gather materials (simplified)
        for fpath in storage_path.glob("*.md"):
             with open(fpath, "r", encoding="utf-8") as f:
                materials.append(f"MD file '{fpath.name}':\n{f.read()}")
        
        combined_materials = "\n\n".join(materials)
        report_content = f"Report materials:\n{combined_materials}"
        
        # Create refiner state wrapper
        # We might need to construct a proper input if refiner expects specific keys
        refiner_input = state.dict() if hasattr(state, "dict") else dict(state)
        refiner_input["messages"] = [HumanMessage(content=report_content)]
        
        result = agent.invoke(refiner_input)
        output = result.get("messages")[-1].content
        
        current_messages = list(get_state_attr(state, "messages", []))
        return {
            "messages": current_messages + [AIMessage(content=output, name=name)],
            "last_active_agent": name,
        }
        
    except Exception as e:
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {"messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name=name)]}

logger.info("Agent processing module initialized")