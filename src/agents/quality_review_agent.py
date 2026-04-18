from typing import Any, Dict, Literal, List, TYPE_CHECKING
from pydantic import BaseModel, Field

from ..tools.basetool import list_directory
from ..tools.FileEdit import create_document, read_document, edit_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.node import get_state_attr
from ..logger import setup_logger

# Initialize logger
logger = setup_logger()

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class QualityOutput(BaseModel):
    """Pydantic model for quality review output."""
    needs_revision: bool = Field(
        description="Indicates if needs revision"
    )
    feedback: str = Field(
        description="Specific feedback on parts that need improvement"
    )

class QualityReviewAgent(BaseAgent):
    """Agent responsible for reviewing and ensuring the quality of research outputs."""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """
        Initialize the QualityReviewAgent.

        Args:
            language_model_manager: Manager for language model configuration.
            team_members: List of team member roles for collaboration.
            working_directory: The directory where the agent's data will be stored.
        """
        super().__init__(
            agent_name="quality_review_agent", 
            language_model_manager=language_model_manager, 
            team_members=team_members, 
            working_directory=working_directory, 
            response_format=QualityOutput
        )

    def _get_tools(self) -> List:
        """Get the list of tools for the QualityReviewAgent."""
        return [create_document, read_document, edit_document, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """Return state updates for quality review decisions.
        
        Manages revision count and quality_feedback lifecycle:
        - When needs_revision=True: stores feedback and increments revision_count
        - When needs_revision=False: clears feedback and resets revision_count
        
        Args:
            state: The current workflow state.
            output: The agent's QualityOutput or a raw string if parsing failed.
            
        Returns:
            Dict with revision control fields.
        """
        # Handle cases where output might be a raw string due to parsing issues
        if isinstance(output, str):
            logger.warning(f"QualityReviewAgent received string instead of QualityOutput: {output[:100]}...")
            # Heuristic: if the agent mentioned revision or improvement, assume needs_revision=True
            needs_revision = any(kw in output.lower() for kw in ["revision", "improve", "fix", "correct", "change"])
            feedback = output
        else:
            needs_revision = getattr(output, "needs_revision", False)
            feedback = getattr(output, "feedback", "")

        updates: Dict[str, Any] = {"needs_revision": needs_revision}
        
        current_count = get_state_attr(state, "revision_count", 0)
        if needs_revision:
            updates["quality_feedback"] = feedback
            updates["revision_count"] = current_count + 1
        else:
            # Review passed: clear feedback and reset counter
            updates["quality_feedback"] = None
            updates["revision_count"] = 0
        
        return updates
