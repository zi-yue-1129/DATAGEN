"""Agent configuration loader with progressive disclosure support.

This module implements a smart loader for agent configurations following the
Claude Agent Skills specification. It supports:
- YAML frontmatter + Markdown format for agent definitions
- Progressive disclosure (Level 1: Metadata, Level 2: Instructions, Level 3: Resources)
- Skills and Rules integration
- MCP server configuration per agent

Example:
    loader = AgentConfigLoader()
    
    # Level 1: Discover agents (lightweight)
    agents = loader.discover_agents()
    
    # Level 2: Load full system prompt when needed
    prompt = loader.load_system_prompt("process_agent")
    
    # Level 3: Load skills and MCP config
    skills = loader.load_skills("process_agent")
    mcp_config = loader.load_mcp_config("process_agent")
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..logger import setup_logger


logger = setup_logger()


@dataclass
class AgentMetadata:
    """Agent metadata extracted from YAML frontmatter (Level 1).

    Attributes:
        name: Unique identifier for the agent (lowercase with hyphens).
        description: Brief description of the agent's purpose.
        version: Semantic version string.
        model: Model configuration dictionary.
        skills: List of skill names to load from shared skills/ folder.
        rules: Path to rules file (string) or list of paths.
        mcp_servers: List of MCP server names to enable.
        use_complete_prompt: If True, use the markdown content as complete system prompt.
    """
    name: str
    description: str
    version: str = "1.0.0"
    model: Dict[str, Any] = field(default_factory=dict)
    skills: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    rules: Any = ""  # Can be str or List[str]
    mcp_servers: List[str] = field(default_factory=list)
    use_complete_prompt: bool = False


@dataclass
class SkillConfig:
    """Skill configuration from SKILL.md file.

    Attributes:
        name: Unique identifier for the skill.
        description: Brief description for discovery and triggering.
        content: Full markdown content of the skill.
        path: Absolute path to the skill file.
    """
    name: str
    description: str
    content: str
    path: Path


@dataclass
class RuleConfig:
    """Rule configuration from rule markdown file.

    Attributes:
        trigger: When the rule applies ('always_on', 'on_demand', 'context_match').
        priority: Priority for rule application (higher = applied first).
        context_patterns: Patterns for context_match trigger.
        content: Full markdown content of the rule.
        path: Absolute path to the rule file.
    """
    trigger: str = "always_on"
    priority: int = 100
    context_patterns: List[str] = field(default_factory=list)
    content: str = ""
    path: Optional[Path] = None


class AgentConfigLoader:
    """Smart loader for agent configurations with progressive disclosure.

    This loader implements a three-level loading strategy:
    - Level 1: Metadata (always loaded, lightweight)
    - Level 2: Instructions/System Prompt (loaded when agent is triggered)
    - Level 3: Skills, Rules, MCP config (loaded on demand)

    Attributes:
        config_root: Root directory for agent configurations.
    """

    # Pattern to extract YAML frontmatter from markdown
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",
        re.DOTALL
    )

    def __init__(
        self,
        config_root: str | Path | None = None,
        mcp_config_path: str | Path | None = None
    ) -> None:
        """Initialize the agent configuration loader.

        Args:
            config_root: Root directory containing agent configurations.
            mcp_config_path: Path to the MCP server configuration file.
        """
        # Load base config directory from environment
        config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
        
        # Set defaults relative to config_dir if not provided
        if config_root is None:
            config_root = os.path.join(config_dir, "agents")
        if mcp_config_path is None:
            mcp_config_path = os.path.join(config_dir, "mcp.yaml")
            
        self.config_root = Path(config_root)
        self.mcp_config_path = Path(mcp_config_path)
        self._metadata_cache: Dict[str, AgentMetadata] = {}
        self._mcp_config: Optional[Dict[str, Any]] = None

    def discover_agents(self) -> List[str]:
        """Discover all available agents (Level 1).

        Scans the config_root directory for agent subdirectories containing
        AGENT.md files.

        Returns:
            List of agent names (directory names).
        """
        agents = []
        if not self.config_root.exists():
            logger.warning(f"Agent config root does not exist: {self.config_root}")
            return agents

        for item in self.config_root.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                agent_md = item / "AGENT.md"
                if agent_md.exists():
                    agents.append(item.name)

        logger.info(f"Discovered {len(agents)} agents: {agents}")
        return agents

    def load_metadata(self, agent_name: str) -> AgentMetadata:
        """Load agent metadata from YAML frontmatter (Level 1).

        Args:
            agent_name: Name of the agent (directory name).

        Returns:
            AgentMetadata dataclass containing frontmatter data.

        Raises:
            FileNotFoundError: If AGENT.md does not exist.
            ValueError: If frontmatter is missing or invalid.
        """
        if agent_name in self._metadata_cache:
            return self._metadata_cache[agent_name]

        agent_md_path = self.config_root / agent_name / "AGENT.md"
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            raise ValueError(f"No frontmatter found in {agent_md_path}")

        # Get extended config from agent_config.yaml
        ext_config = self._get_agent_extended_config(agent_name)

        metadata = AgentMetadata(
            name=frontmatter.get("name", agent_name),
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            model=frontmatter.get("model", {}),
            # Read skills/rules/mcp from agent_config.yaml, not frontmatter
            skills=ext_config.get("skills", []),
            tools=ext_config.get("tools", []),
            rules=ext_config.get("rules", []),
            mcp_servers=ext_config.get("mcp_servers", []),
            use_complete_prompt=frontmatter.get("use_complete_prompt", False),
        )

        self._metadata_cache[agent_name] = metadata
        return metadata

    def load_system_prompt(self, agent_name: str) -> str:
        """Load full system prompt from AGENT.md (Level 2).

        Extracts the markdown content after the frontmatter as the system prompt.

        Args:
            agent_name: Name of the agent.

        Returns:
            System prompt string (markdown content).

        Raises:
            FileNotFoundError: If AGENT.md does not exist.
        """
        agent_md_path = self.config_root / agent_name / "AGENT.md"
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")
        
        # Remove frontmatter to get the prompt content
        match = self.FRONTMATTER_PATTERN.match(content)
        if match:
            prompt = content[match.end():].strip()
        else:
            prompt = content.strip()

        # Load and apply rules
        rules_content = self._load_rules_content(agent_name)
        if rules_content:
            prompt = f"{prompt}\n\n{rules_content}"

        # Load and apply skills
        skills_content = self._load_skills_content(agent_name)
        if skills_content:
            prompt = f"{prompt}\n\n{skills_content}"

        metadata = self.load_metadata(agent_name)
        if metadata.use_complete_prompt:
            return f"SYSTEM_PROMPT:{prompt}"
        
        return prompt

    def load_skills(self, agent_name: str) -> List[SkillConfig]:
        """Load agent-specific skills (Level 3).

        Args:
            agent_name: Name of the agent.

        Returns:
            List of SkillConfig objects.
        """
        metadata = self.load_metadata(agent_name)
        skills = []
        # Skills folder is at config/skills/ (sibling of agents/)
        skills_dir = self.config_root.parent / "skills"

        for skill_name in metadata.skills:
            # Skills are referenced by name, stored in shared skills/ folder
            skill_path = skills_dir / skill_name / "SKILL.md"
            if skill_path.exists():
                skill = self._parse_skill_file(skill_path)
                if skill:
                    skills.append(skill)
            else:
                logger.warning(f"Skill not found: {skill_name}")

        return skills

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """Get the full content of a skill file (Level 2).

        Args:
            skill_name: Name of the skill.

        Returns:
            Content of the SKILL.md file or None if not found.
        """
        # Skills folder is at config/skills/ (sibling of agents/)
        skills_dir = self.config_root.parent / "skills"
        skill_path = skills_dir / skill_name / "SKILL.md"
        
        if not skill_path.exists():
            logger.warning(f"Skill file not found: {skill_path}")
            return None
            
        return skill_path.read_text(encoding="utf-8")

    def load_rules(self, agent_name: str) -> List[RuleConfig]:
        """Load applicable rules for an agent (Level 3).

        Args:
            agent_name: Name of the agent.

        Returns:
            List of RuleConfig objects, sorted by priority (descending).
        """
        metadata = self.load_metadata(agent_name)
        rules = []

        # Rules is now a single file path (string) instead of list
        rule_path = metadata.rules
        if not rule_path:
            return rules

        # Handle as string (single file) or list for backward compatibility
        if isinstance(rule_path, str):
            rule_paths = [rule_path]
        else:
            rule_paths = rule_path

        for rp in rule_paths:
            # Paths starting with '_' are relative to config_root (shared)
            if rp.startswith("_"):
                full_path = (self.config_root / rp).resolve()
            else:
                agent_dir = self.config_root / agent_name
                full_path = (agent_dir / rp).resolve()

            if full_path.exists():
                rule = self._parse_rule_file(full_path)
                if rule:
                    rules.append(rule)
            else:
                logger.warning(f"Rule file not found: {full_path}")

        # Sort by priority (higher first)
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules

    def load_mcp_config(self, agent_name: str) -> Dict[str, Any]:
        """Load MCP server configuration for an agent (Level 3).

        Combines default MCP servers with agent-specific overrides.

        Args:
            agent_name: Name of the agent.

        Returns:
            Dictionary with 'servers' key containing enabled server configs.
        """
        if self._mcp_config is None:
            self._mcp_config = self._load_mcp_config_file()

        metadata = self.load_metadata(agent_name)
        all_servers = self._mcp_config.get("servers", {})
        defaults = self._mcp_config.get("defaults", [])

        # Combine default servers with agent-specific servers
        enabled_servers = set(defaults) | set(metadata.mcp_servers)

        result = {
            "servers": {
                name: config
                for name, config in all_servers.items()
                if name in enabled_servers
            }
        }

        return result

    def get_model_config(self, agent_name: str) -> Dict[str, Any]:
        """Get model configuration from agent metadata.

        Args:
            agent_name: Name of the agent.

        Returns:
            Dictionary containing provider and model config.
        """
        metadata = self.load_metadata(agent_name)
        return metadata.model

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract YAML frontmatter from markdown content.

        Args:
            content: Full markdown file content.

        Returns:
            Parsed YAML dictionary or None if no frontmatter.
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse frontmatter: {e}")
            return None

    def _parse_skill_file(self, path: Path) -> Optional[SkillConfig]:
        """Parse a SKILL.md file into SkillConfig.

        Args:
            path: Path to the skill file.

        Returns:
            SkillConfig or None if parsing fails.
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            logger.warning(f"No frontmatter in skill file: {path}")
            return None

        return SkillConfig(
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            content=content,
            path=path,
        )

    def _parse_rule_file(self, path: Path) -> Optional[RuleConfig]:
        """Parse a rule markdown file into RuleConfig.

        Args:
            path: Path to the rule file.

        Returns:
            RuleConfig or None if parsing fails.
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            # Rules without frontmatter default to always_on
            return RuleConfig(
                trigger="always_on",
                priority=100,
                content=content,
                path=path,
            )

        # Remove frontmatter from content
        match = self.FRONTMATTER_PATTERN.match(content)
        rule_content = content[match.end():].strip() if match else content

        return RuleConfig(
            trigger=frontmatter.get("trigger", "always_on"),
            priority=frontmatter.get("priority", 100),
            context_patterns=frontmatter.get("context_patterns", []),
            content=rule_content,
            path=path,
        )

    def _load_rules_content(self, agent_name: str) -> str:
        """Load and combine rule contents for an agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Combined rule content string.
        """
        rules = self.load_rules(agent_name)
        active_rules = [r for r in rules if r.trigger == "always_on"]
        
        if not active_rules:
            return ""

        sections = ["## Applied Rules"]
        for rule in active_rules:
            sections.append(rule.content)

        return "\n\n".join(sections)

    def _load_skills_content(self, agent_name: str) -> str:
        """Load and combine skill contents for an agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            Combined skill content string.
        """
        skills = self.load_skills(agent_name)
        
        if not skills:
            return ""

        sections = ["## Available Skills"]
        for skill in skills:
            sections.append(f"### {skill.name}\n{skill.description}")

        return "\n\n".join(sections)

    def _load_mcp_config_file(self) -> Dict[str, Any]:
        """Load MCP configuration from YAML file.

        Returns:
            MCP configuration dictionary.
        """
        if not self.mcp_config_path.exists():
            logger.warning(f"MCP config not found: {self.mcp_config_path}")
            return {"servers": {}, "defaults": []}

        try:
            content = self.mcp_config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content)
            
            # Expand environment variables in config
            return self._expand_env_vars(config)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse MCP config: {e}")
            return {"servers": {}, "defaults": []}

    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand environment variables in config.

        Supports ${VAR_NAME} syntax.

        Args:
            obj: Configuration object (dict, list, or string).

        Returns:
            Object with environment variables expanded.
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # Match ${VAR_NAME} pattern
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match: re.Match) -> str:
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return pattern.sub(replace, obj)
        return obj

    def _load_per_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Load per-agent configuration from config.yaml.

        Args:
            agent_name: Name of the agent.

        Returns:
            Agent configuration dictionary.
        """
        config_path = self.config_root / agent_name / "config.yaml"
        if not config_path.exists():
            logger.debug(f"No config.yaml for agent: {agent_name}")
            return {"skills": [], "tools": [], "rules": [], "mcp_servers": []}

        try:
            content = config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content) or {}
            return {
                "skills": config.get("skills", []),
                "tools": config.get("tools", []),
                "rules": config.get("rules", []),
                "mcp_servers": config.get("mcp_servers", []),
            }
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse config.yaml for {agent_name}: {e}")
            return {"skills": [], "tools": [], "rules": [], "mcp_servers": []}

    def _get_agent_extended_config(self, agent_name: str) -> Dict[str, Any]:
        """Get extended configuration (skills/rules/mcp) for an agent.

        Reads from the agent's own config.yaml file.

        Args:
            agent_name: Name of the agent.

        Returns:
            Dictionary with skills, rules, and mcp_servers.
        """
        return self._load_per_agent_config(agent_name)



# Singleton instance for global access
_default_loader: Optional[AgentConfigLoader] = None


def get_agent_config_loader() -> AgentConfigLoader:
    """Get the default AgentConfigLoader singleton.

    Returns:
        AgentConfigLoader instance.
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentConfigLoader()
    return _default_loader
