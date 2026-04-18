from __future__ import annotations
from .state import State
from typing import Literal, Union, cast, Any
from langchain_core.messages import AIMessage
import logging
import json

# Set up logger
logger = logging.getLogger(__name__)

# Define types for node routing
NodeType = Literal['Visualization', 'Search', 'Coder', 'Report', 'Process', 'NoteTaker', 'Hypothesis', 'QualityReview']
ProcessNodeType = Literal['Coder', 'Search', 'Visualization', 'Report', 'Process', 'Refiner']

def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
    """Helper to safely get attributes from State whether it's Pydantic or dict."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)

def hypothesis_router(state: State) -> NodeType:
    """
    Route based on the presence of a hypothesis in the state.
    """
    logger.info("Entering hypothesis_router")
    # Semantic change: check 'current_instruction' instead of 'process'
    current_instruction = get_state_attr(state, "current_instruction")
    
    if current_instruction == "Continue the research process":
        return "Process"
    else:
        return "Hypothesis"

def QualityReview_router(state: State) -> str:
    """
    Route based on the quality review outcome and process decision.
    """
    logger.info("Entering QualityReview_router")
    messages = get_state_attr(state, "messages", [])
    needs_revision = get_state_attr(state, "needs_revision", False)
    revision_count = get_state_attr(state, "revision_count", 0)
    MAX_REVISIONS = 3
    
    # Check if revision is needed
    if needs_revision:
        # Check for infinite loop / max revisions
        if revision_count > MAX_REVISIONS:
            logger.warning(f"Max revisions ({MAX_REVISIONS}) reached. Forcing progression to NoteTaker.")
            return "NoteTaker"

        previous_node = messages[-2].name if len(messages) >= 2 else "NoteTaker"
        revision_routes = {
            "visualization_agent": "Visualization",
            "search_agent": "Search",
            "code_agent": "Coder",
            "report_agent": "Report"
        }
        result = revision_routes.get((str(previous_node)), "NoteTaker")
        logger.info(f"Revision needed. Routing to: {result}")
        return result
    
    else:
        return "NoteTaker"
    

def process_router(state: State) -> ProcessNodeType:
    """
    Route based on the process decision in the state.
    """
    logger.info("Entering process_router")
    # Semantic change: 'next_workflow_step' instead of 'process_decision'
    next_step = get_state_attr(state, "next_workflow_step", "")
    
    valid_decisions = {"Coder", "Search", "Visualization", "Report"}
    
    if next_step in valid_decisions:
        return cast(ProcessNodeType, next_step)
    
    if next_step == "FINISH":
        return "Refiner"
    
    logger.warning(f"Invalid decision: {next_step}. Defaulting to 'Process'.")
    return "Process"

logger.info("Router module initialized")
