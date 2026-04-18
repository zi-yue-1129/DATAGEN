from pydantic import BaseModel, Field
from typing import Sequence, List, TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage

from ..tools.FileEdit import read_document
from ..tools.basetool import list_directory
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.state import State

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager


class NoteOutput(BaseModel):
    """Pydantic model for note agent output."""
    messages: List[Any] = Field(default_factory=list, description="New messages to add or update")
    hypothesis: str = Field(default="", description="Updated research hypothesis")
    current_instruction: str = Field(default="", description="Updated current instruction")
    next_workflow_step: str = Field(default="", description="Updated next workflow step")
    search_artifacts: str = Field(default="", description="Search findings to archive")
    data_viz_artifacts: str = Field(default="", description="Visualization artifacts to archive")
    code_artifacts: str = Field(default="", description="Code artifacts to archive")
    report_artifacts: str = Field(default="", description="Report sections to archive")
    quality_feedback: str = Field(default="", description="Quality feedback if any")
    needs_revision: bool = Field(default=False, description="Whether revision is needed")

class NoteAgent(BaseAgent):
    """Agent responsible for taking notes on the research process."""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """
        Initialize the NoteAgent.

        Args:
            language_model_manager: Manager for language model configuration.
            team_members: List of team member roles for collaboration.
            working_directory: The directory where the agent's data will be stored.
        """
        super().__init__(
            agent_name="note_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=NoteOutput
        )

    def _get_tools(self) -> List:
        """Get the tools for NoteAgent."""
        return [read_document, list_directory]
