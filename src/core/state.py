from __future__ import annotations
from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class State(BaseModel):
    """
    Canonical shared state for the multi-agent research workflow.
    Designed as an 'Action Log' and 'Artifact Digest'.
    """
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True, 
        validate_assignment=True,
        extra='ignore'
    )

    # === Context Layer ===
    messages: Annotated[list[BaseMessage], add_messages] = Field(
        default_factory=list,
        description="Sequence of messages exchanged in the workflow"
    )
    last_active_agent: str | None = Field(
        default=None, 
        description="The last agent that performed an action"
    )
    step_count: int = Field(
        default=0, 
        description="Safety counter to prevent infinite loops"
    )

    # === Workflow Control ===
    current_instruction: str | None = Field(
        default=None, 
        description="Specific task assigned to the next agent"
    )
    next_workflow_step: str | None = Field(
        default=None, 
        description="The next node/agent to route to"
    )
    
    # === Task Tracking ===
    todo_list: list[str] = Field(
        default_factory=list, 
        description="List of pending subtasks"
    )
    completed_tasks: list[str] = Field(
        default_factory=list, 
        description="List of completed subtasks"
    )

    # === Domain Artifacts (Dict[Path, Description]) ===
    hypothesis: str | None = Field(
        default=None, 
        description="Current research hypothesis"
    )
    
    search_artifacts: dict[str, str] = Field(
        default_factory=dict, 
        description="Map of {path: summary} for search results"
    )
    data_viz_artifacts: dict[str, str] = Field(
        default_factory=dict, 
        description="Map of {path: summary} for visualizations"
    )
    code_artifacts: dict[str, str] = Field(
        default_factory=dict, 
        description="Map of {path: summary} for code files"
    )
    report_artifacts: dict[str, str] = Field(
        default_factory=dict, 
        description="Map of {section: path/content} for report sections"
    )

    # === Review Loop ===
    quality_feedback: str | None = Field(
        default=None, 
        description="Feedback from quality review"
    )
    needs_revision: bool = Field(
        default=False, 
        description="Flag to trigger revision loop"
    )
    revision_count: int = Field(
        default=0,
        description="Counter for consecutive revision attempts"
    )
    
    # === Legacy Compatibility (Optional) ===
    # Using properties or aliases if needed, but we are doing a hard break as requested.


def create_initial_state(user_input: str) -> dict[str, Any]:
    """
    Factory function to create the initial state dictionary for LangGraph.
    """
    return {
        "messages": [HumanMessage(content=user_input)],
        "last_active_agent": "user",
        "step_count": 0,
        "todo_list": [],
        "completed_tasks": [],
        "search_artifacts": {},
        "data_viz_artifacts": {},
        "code_artifacts": {},
        "report_artifacts": {},
        "needs_revision": False,
        "revision_count": 0
    }
