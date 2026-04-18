from __future__ import annotations
"""Centralized configuration for tool security and resource limits.

This module provides dataclasses for tool limits and a configuration manager
that loads settings from YAML with fallback to defaults.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os
import yaml
from pathlib import Path

from ..logger import setup_logger

logger = setup_logger()

# Default constants
DEFAULT_MAX_OUTPUT_CHARS = 50000
DEFAULT_MAX_READ_BYTES = 5 * 1024 * 1024  # 5MB
DEFAULT_MAX_READ_LINES = 10000
DEFAULT_MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10MB


@dataclass
class ExecutionLimits:
    """Resource limits for code execution.
    
    Attributes:
        timeout_seconds: Max execution time. None = no limit.
        max_memory_mb: Max memory usage (Linux only). None = no limit.
        max_output_chars: Truncate output if exceeds this limit.
        progress_timeout_seconds: If set, timeout resets on stdout activity.
        blocked_patterns: Code patterns to block (security).
    """
    timeout_seconds: Optional[int] = None
    max_memory_mb: Optional[int] = None
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    progress_timeout_seconds: Optional[int] = None
    blocked_patterns: List[str] = field(default_factory=lambda: [
        "os.system",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "shutil.rmtree",
        "eval(",
        "exec(",
        "__import__",
    ])


@dataclass
class FileOperationLimits:
    """Limits for file read/write operations.
    
    Attributes:
        max_read_bytes: Maximum file size to read.
        max_read_lines: Maximum lines to return.
        max_write_bytes: Maximum content size to write.
        allowed_extensions: Whitelist of allowed file extensions.
        blocked_paths: Paths that cannot be accessed.
    """
    max_read_bytes: int = DEFAULT_MAX_READ_BYTES
    max_read_lines: int = DEFAULT_MAX_READ_LINES
    max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES
    allowed_extensions: List[str] = field(default_factory=lambda: [
        ".py", ".md", ".txt", ".csv", ".json", ".yaml", ".yml",
        ".log", ".png", ".jpg", ".jpeg", ".html", ".css", ".js"
    ])
    blocked_paths: List[str] = field(default_factory=lambda: [
        "/etc", "/sys", "/proc", "/root", "~/.ssh", "/var/log"
    ])


class ToolConfig:
    """Central configuration manager for all tools.
    
    Loads settings from YAML config file with fallback to defaults.
    Provides a singleton-like access pattern via the global TOOL_CONFIG.
    """

    def __init__(
        self,
        execution: Optional[ExecutionLimits] = None,
        file_ops: Optional[FileOperationLimits] = None,
        enable_security_scan: bool = True,
        enable_write_validation: bool = True
    ):
        """Initialize tool configuration.
        
        Args:
            execution: Execution limits configuration.
            file_ops: File operation limits configuration.
            enable_security_scan: Whether to scan code for dangerous patterns.
            enable_write_validation: Whether to validate content before writing.
        """
        self.execution = execution or ExecutionLimits()
        self.file_ops = file_ops or FileOperationLimits()
        self.enable_security_scan = enable_security_scan
        self.enable_write_validation = enable_write_validation

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> ToolConfig:
        """Load configuration from YAML file with defaults as fallback.
        
        Args:
            config_path: Path to YAML config file (relative to project root).
            
        Returns:
            ToolConfig instance with loaded or default settings.
        """
        if config_path is None:
            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            config_path = os.path.join(config_dir, "tool_limits.yaml")
        settings = {}

        # Try multiple paths to find the config
        possible_paths = [
            Path(config_path),
            Path(os.getcwd()) / config_path,
            Path(__file__).parent.parent.parent.parent / config_path,
        ]

        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        settings = yaml.safe_load(f) or {}
                    logger.info(f"Loaded tool limits from {path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to load tool limits from {path}: {e}")

        if not settings:
            logger.debug("Tool limits config not found, using defaults")

        # Parse execution settings
        exec_settings = settings.get("execution", {})
        exec_limits = ExecutionLimits(
            timeout_seconds=exec_settings.get("timeout_seconds"),
            max_memory_mb=exec_settings.get("max_memory_mb"),
            max_output_chars=exec_settings.get("max_output_chars", 50000),
            progress_timeout_seconds=exec_settings.get("progress_timeout_seconds"),
            blocked_patterns=exec_settings.get("blocked_patterns", ExecutionLimits().blocked_patterns),
        )

        # Parse file operation settings
        file_settings = settings.get("file_operations", {})
        file_limits = FileOperationLimits(
            max_read_bytes=file_settings.get("max_read_bytes", 5 * 1024 * 1024),
            max_read_lines=file_settings.get("max_read_lines", 10000),
            max_write_bytes=file_settings.get("max_write_bytes", 10 * 1024 * 1024),
            allowed_extensions=file_settings.get("allowed_extensions", FileOperationLimits().allowed_extensions),
            blocked_paths=file_settings.get("blocked_paths", FileOperationLimits().blocked_paths),
        )

        return cls(
            execution=exec_limits,
            file_ops=file_limits,
            enable_security_scan=settings.get("enable_security_scan", True),
            enable_write_validation=settings.get("enable_write_validation", True),
        )

    def to_dict(self) -> dict:
        """Export current configuration as dictionary."""
        return {
            "execution": {
                "timeout_seconds": self.execution.timeout_seconds,
                "max_memory_mb": self.execution.max_memory_mb,
                "max_output_chars": self.execution.max_output_chars,
                "progress_timeout_seconds": self.execution.progress_timeout_seconds,
                "blocked_patterns": self.execution.blocked_patterns,
            },
            "file_operations": {
                "max_read_bytes": self.file_ops.max_read_bytes,
                "max_read_lines": self.file_ops.max_read_lines,
                "max_write_bytes": self.file_ops.max_write_bytes,
                "allowed_extensions": self.file_ops.allowed_extensions,
                "blocked_paths": self.file_ops.blocked_paths,
            },
            "enable_security_scan": self.enable_security_scan,
            "enable_write_validation": self.enable_write_validation,
        }


# Global singleton instance
try:
    TOOL_CONFIG = ToolConfig.load()
except Exception as e:
    logger.error(f"Error initializing ToolConfig: {e}, using defaults")
    TOOL_CONFIG = ToolConfig()
