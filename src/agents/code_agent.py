from typing import Any, Dict, List, TYPE_CHECKING

from ..tools.basetool import execute_code, execute_command, list_directory
from ..tools.FileEdit import read_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.schemas import ArtifactSchema
from ..core.node import update_artifact_dict, get_state_attr

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class CodeAgent(BaseAgent):
    """Agent responsible for writing and executing Python code for data processing."""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """
        Initialize the CodeAgent.

        Args:
            language_model_manager: Manager for language model configuration.
            team_members: List of team member roles for collaboration.
            working_directory: The directory where the agent's data will be stored.
        """
        super().__init__(
            agent_name="code_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )
        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """Get the list of tools for code generation and execution."""
        return [read_document, execute_code, execute_command, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """Return state updates for code artifacts.
        
        Args:
            state: The current workflow state.
            output: The agent's ArtifactSchema output or a dict.
            
        Returns:
            Dict with 'code_artifacts' field update.
        """
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        current = get_state_attr(state, "code_artifacts", {})
        # If output contains 'artifacts' key/attr, use it, otherwise use the whole output
        new_data = safe_get(output, "artifacts", output)
        
        return {"code_artifacts": update_artifact_dict(current, new_data)}

