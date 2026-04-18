from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, List, TYPE_CHECKING

from ..core.language_models import LanguageModelManager
from .base import BaseAgent
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:
    from ..core.state import State

class ProcessRouteSchema(BaseModel):
    """Select the next role and assign a task.
    
    Attributes:
        next_workflow_step: The next role to act (Visualization, Search, Coder, Report, or FINISH).
        current_instruction: The detailed task description to be performed by the selected agent.
        todo_list: A list of pending subtasks to be completed.
    """
    next_workflow_step: Literal["FINISH", "Visualization", "Search", "Coder", "Report"] = Field(
        description="The next role to act"
    )
    current_instruction: str = Field(
        description="The detailed instruction for the next agent"
    )
    todo_list: List[str] = Field(
        default_factory=list,
        description="Current list of pending tasks for the project"
    )
    
class ProcessAgent(BaseAgent):
    """Agent responsible for overseeing and coordinating the data analysis project."""

    def __init__(self, language_model_manager: LanguageModelManager, team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """Initialize the ProcessAgent.

        Args:
            language_model_manager: Manager for language model configuration.
            team_members: List of team member roles for collaboration.
            working_directory: The directory where the agent's data will be stored.
                               Defaults to WORKING_DIRECTORY config.
        """
        super().__init__(
            agent_name="process_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=ProcessRouteSchema
        )

    def _get_tools(self) -> List:
        """Not used in this agent."""
        return []

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """Return state updates for process routing decisions.
        
        Args:
            state: The current workflow state.
            output: The agent's ProcessRouteSchema output or a dict.
            
        Returns:
            Dict with workflow routing fields.
        """
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        return {
            "current_instruction": safe_get(output, "current_instruction", safe_get(output, "task", "")),
            "next_workflow_step": safe_get(output, "next_workflow_step", safe_get(output, "next", "")),
            "todo_list": safe_get(output, "todo_list", [])
        }