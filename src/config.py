import os
from dotenv import load_dotenv
import yaml
# Load environment variables
load_dotenv()

# Set up API keys and environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
# fastCRW (Firecrawl-compatible web scraper; single binary, self-host or cloud)
CRW_API_KEY = os.getenv('CRW_API_KEY')
# Default to managed cloud; override CRW_API_URL for self-host (e.g. http://localhost:3000)
CRW_API_URL = os.getenv('CRW_API_URL', 'https://fastcrw.com/api')
# Get working directory from environment variable
WORKING_DIRECTORY = os.getenv('WORKING_DIRECTORY', './data')
# Get Conda-related paths from environment variables
CONDA_ENV = os.getenv('CONDA_ENV', 'base')
# Get ChromeDriver
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', './chromedriver/chromedriver')
# Get Config Directory
CONFIG_DIRECTORY = os.getenv('CONFIG_DIRECTORY', 'config')


class AgentModelsConfig:
    """Configuration class for loading agent models from YAML file."""

    def __init__(self, config_path: str = 'config/agent_models.yaml'):
        """Initialize the configuration by loading the YAML file.

        Args:
            config_path: Path to the YAML configuration file.

        Raises:
            FileNotFoundError: If the configuration file does not exist.
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                self._config = yaml.safe_load(file)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Configuration file not found: {config_path}") from e

    @property
    def agents(self):
        """Get the agents configuration."""
        return self._config.get('agents', {})

    def get_agent_config(self, agent_name: str):
        """Get configuration for a specific agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Agent configuration dictionary or empty dict if not found.
        """
        return self.agents.get(agent_name, {})

    def get_provider(self, agent_name: str):
        """Get the provider for a specific agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Provider name or None if not found.
        """
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('provider')

    def get_model_config(self, agent_name: str):
        """Get the model configuration for a specific agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Model configuration dictionary or empty dict if not found.
        """
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('model_config', {})


# Create global instance
AGENT_MODELS = AgentModelsConfig(os.path.join(CONFIG_DIRECTORY, 'agent_models.yaml'))