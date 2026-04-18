from __future__ import annotations
from typing import Any, Union, TYPE_CHECKING
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
import logging
import json
from pathlib import Path
import time

from .state import State
from ..config import WORKING_DIRECTORY

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
    """Safely extract content from output (Pydantic, dict, or str).
    
    Args:
        output: The agent output (Pydantic model, dict, or string).
        keys: Priority list of attribute/key names to try.
        default: Default value if no key found.
        
    Returns:
        Extracted string content.
    """
    if isinstance(output, str):
        return output
    for key in keys:
        if isinstance(output, dict):
            if key in output:
                return str(output[key])
        elif hasattr(output, key):
            val = getattr(output, key, None)
            if val is not None:
                return str(val)
    return str(output) if output else default

def agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """Process an agent's action and update the state accordingly."""
    logger.info(f"Processing agent: {name}")
    try:
        result = agent.invoke(state)
        
        # Generic handling for structured output
        if "structured_response" in result:
            output = result["structured_response"]
            # Extract meaningful content for the message history using safe helper
            content = safe_get_content(output, ["task", "feedback", "summary"])
            ai_message = AIMessage(content=content, name=name)
        else:
            # Standard agents usually return a dict with messages
            message = result.get("messages")[-1]
            output = message.content
            ai_message = AIMessage(content=output, name=name)

        # Base Updates
        updates = {
            "messages": [ai_message],
            "last_active_agent": name
        }

        # StateUpdater Protocol: call agent's get_state_updates if available
        # All agents should implement this method for their specific state mappings
        if hasattr(agent, "get_state_updates"):
            # Pass the structured object if available, otherwise pass the raw string
            # This ensures agents like QualityReviewAgent receive the QualityOutput model
            update_source = output
            if "structured_response" in result:
                update_source = result["structured_response"]
            
            agent_updates = agent.get_state_updates(state, update_source)
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
        return {
            "messages": [AIMessage(content=f"Error: {str(e)}", name=name)],
            "last_active_agent": name
        }

def human_choice_node(state: State) -> dict[str, Any]:
    """Handle human input to choose the next step."""
    print("Please choose the next step:")
    print("1. Regenerate hypothesis")
    print("2. Continue the research process")
    
    while True:
        choice = input("Please enter your choice (1 or 2): ")
        if choice in ["1", "2"]:
            break
        print("Invalid input, please try again.")
    
    updates = {
        "messages": [],
        "last_active_agent": "human"
    }
    
    if choice == "1":
        modification_areas = input("Specify areas to modify: ")
        updates["messages"] = [HumanMessage(content=f"Regenerate hypothesis. Areas: {modification_areas}")]
        updates["hypothesis"] = None  # Clear hypothesis
    else:
        updates["messages"] = [HumanMessage(content="Continue the research process")]
        updates["current_instruction"] = "Continue the research process"
    
    return updates

def create_message(message: BaseMessage, name: str) -> BaseMessage:
    """Create a BaseMessage object based on the message type."""
    content = message.content
    message_type = message.type.lower()
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
        output = result.get("structured_response")
        
        if not output:
            logger.error(f"Note agent {name} failed to return structured_response")
            return _create_error_state(state, AIMessage(content=f"Error: Agent {name} failed to return structured response", name=name), name, "Missing structured response")

        new_messages = [create_message(msg, name) for msg in output.messages]
        messages: list[BaseMessage] = list(new_messages) if new_messages else list(processing_messages)
        combined_messages = head_messages + messages + tail_messages
        
        # Map NoteState output fields to New State Schema
        updated_state = {
            "messages": combined_messages,
            "hypothesis": str(getattr(output, "hypothesis", "")),
            
            # Semantic Mapping: Try new field first, then legacy
            "current_instruction": str(getattr(output, "current_instruction", getattr(output, "process", ""))),
            "next_workflow_step": str(getattr(output, "next_workflow_step", getattr(output, "process_decision", ""))),
            
            # Artifact Mapping
            "search_artifacts": update_artifact_dict({}, str(getattr(output, "search_artifacts", getattr(output, "searcher_state", "")))),
            "data_viz_artifacts": update_artifact_dict({}, str(getattr(output, "data_viz_artifacts", getattr(output, "visualization_state", "")))),
            "code_artifacts": update_artifact_dict({}, str(getattr(output, "code_artifacts", getattr(output, "code_state", "")))),
            "report_artifacts": update_artifact_dict({}, str(getattr(output, "report_artifacts", getattr(output, "report_section", "")))),
            
            "quality_feedback": str(getattr(output, "quality_feedback", getattr(output, "quality_review", ""))),
            "needs_revision": bool(getattr(output, "needs_revision", False)),
            
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
        print("Current research progress:")
        print(state)
        print("\nDo you need additional analysis or modifications?")
        
        while True:
            user_input = input("Enter 'yes' to continue analysis, or 'no' to end the research: ").lower()
            if user_input in ['yes', 'no']:
                break
        
        updates: dict[str, Any] = {"last_active_agent": "human"}
        
        if user_input == 'yes':
            while True:
                req = input("Please enter your request: ").strip()
                if req:
                    updates["messages"] = [HumanMessage(content=req)]
                    updates["needs_revision"] = True
                    break
        else:
            updates["needs_revision"] = False
            updates["revision_count"] = 0
        
        return updates
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {"messages": [AIMessage(content=f"Error: {str(e)}", name="human_review")]}

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
        
        return {
            "messages": [AIMessage(content=output, name=name)],
            "last_active_agent": name,
            # Refiner usually outputs the final report or refinement
            # We could map this to 'report_artifacts' or just messages for now
        }
        
    except Exception as e:
        logger.error(f"Error in refiner_node: {str(e)}", exc_info=True)
        return {"messages": [AIMessage(content=f"Error: {str(e)}", name=name)]}

logger.info("Agent processing module initialized")