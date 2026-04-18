"""MCP (Model Context Protocol) server manager with real client integration.

This module provides management of MCP server connections and tool exposure
for agents. It uses the official MCP Python SDK for real server communication
via stdio transport.

Reference: https://modelcontextprotocol.io/

Example:
    manager = get_mcp_manager()
    
    # Discover tools from a server
    tools = await manager.discover_tools("filesystem")
    
    # Call a tool
    result = await manager.call_tool("filesystem", "read_file", {"path": "README.md"})
    
    # Close all connections when done
    await manager.close_all()
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..logger import setup_logger


logger = setup_logger()


# Constants
MCP_SERVER_STOP_TIMEOUT = 5
CONNECTION_TIMEOUT = 30


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server.

    Attributes:
        name: Server identifier.
        command: Command to start the server.
        args: Command line arguments.
        env: Environment variables for the server.
        description: Human-readable description.
    """
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class MCPResource:
    """A resource exposed by an MCP server.

    Attributes:
        uri: Unique resource identifier.
        name: Human-readable name.
        mime_type: MIME type of the resource.
        description: Optional description.
    """
    uri: str
    name: str
    mime_type: str = "text/plain"
    description: str = ""


@dataclass
class MCPTool:
    """A tool exposed by an MCP server.

    Attributes:
        name: Tool identifier.
        description: Human-readable description.
        input_schema: JSON schema for tool input.
        server_name: Name of the server providing this tool.
    """
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPServerConnection:
    """Active connection to an MCP server.

    Attributes:
        name: Server name identifier.
        session: The MCP ClientSession for communication.
        cleanup: Async cleanup function to call on disconnect.
    """
    name: str
    session: Any  # mcp.ClientSession
    cleanup: Any  # Coroutine to cleanup connection


class MCPManager:
    """Manages MCP server connections and tool exposure.

    This manager handles:
    - Loading MCP server configurations
    - Starting and stopping MCP servers via stdio transport
    - Discovering tools and resources from servers
    - Calling tools on connected servers
    - Providing tools to agents based on their configuration

    Attributes:
        config_path: Path to the MCP configuration file.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize the MCP manager.

        Args:
            config_path: Path to the MCP configuration file.
        """
        if config_path is None:
            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            config_path = os.path.join(config_dir, "mcp.yaml")
            
        self.config_path = Path(config_path)
        self._config: Optional[Dict[str, Any]] = None
        self._servers: Dict[str, MCPServerConfig] = {}
        self._connections: Dict[str, MCPServerConnection] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    @property
    def config(self) -> Dict[str, Any]:
        """Lazy-load MCP configuration.

        Returns:
            Configuration dictionary.
        """
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def get_server_config(self, name: str) -> Optional[MCPServerConfig]:
        """Get configuration for a specific MCP server.

        Args:
            name: Server name.

        Returns:
            MCPServerConfig or None if not found.
        """
        if name in self._servers:
            return self._servers[name]

        servers = self.config.get("servers", {})
        if name not in servers:
            logger.warning(f"MCP server not found: {name}")
            return None

        server_config = servers[name]
        mcp_config = MCPServerConfig(
            name=name,
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            env=server_config.get("env", {}),
            description=server_config.get("description", ""),
        )
        self._servers[name] = mcp_config
        return mcp_config

    def get_enabled_servers(self, agent_name: str) -> List[MCPServerConfig]:
        """Get list of MCP servers enabled for an agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            List of MCPServerConfig for enabled servers.
        """
        from .agent_config_loader import get_agent_config_loader

        loader = get_agent_config_loader()
        mcp_config = loader.load_mcp_config(agent_name)

        servers = []
        for name in mcp_config.get("servers", {}).keys():
            config = self.get_server_config(name)
            if config:
                servers.append(config)

        return servers

    async def connect(self, server_name: str) -> bool:
        """Connect to an MCP server via stdio transport.

        Args:
            server_name: Name of the server to connect to.

        Returns:
            True if connection successful, False otherwise.
        """
        # Get or create lock for this server
        async with self._global_lock:
            if server_name not in self._connection_locks:
                self._connection_locks[server_name] = asyncio.Lock()

        async with self._connection_locks[server_name]:
            # Already connected?
            if server_name in self._connections:
                logger.debug(f"Already connected to MCP server: {server_name}")
                return True

            config = self.get_server_config(server_name)
            if not config:
                return False

            try:
                # Import MCP SDK
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                # Prepare environment
                env = os.environ.copy()
                for key, value in config.env.items():
                    env[key] = value

                # Create server parameters
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=env,
                )

                logger.info(f"Connecting to MCP server: {server_name}")
                logger.debug(f"  Command: {config.command} {' '.join(config.args)}")

                # Create the connection context
                # Note: We need to manage the context manually for long-lived connections
                client_context = stdio_client(server_params)
                read_stream, write_stream = await client_context.__aenter__()

                session_context = ClientSession(read_stream, write_stream)
                session = await session_context.__aenter__()

                # Initialize the session
                await asyncio.wait_for(
                    session.initialize(),
                    timeout=CONNECTION_TIMEOUT
                )

                # Store cleanup function
                async def cleanup():
                    try:
                        await session_context.__aexit__(None, None, None)
                        await client_context.__aexit__(None, None, None)
                    except Exception as e:
                        logger.warning(f"Error during MCP cleanup: {e}")

                self._connections[server_name] = MCPServerConnection(
                    name=server_name,
                    session=session,
                    cleanup=cleanup,
                )

                logger.info(f"Connected to MCP server: {server_name}")
                return True

            except ImportError as e:
                logger.error(f"MCP SDK not installed: {e}")
                logger.error("Please install: pip install mcp")
                return False
            except asyncio.TimeoutError:
                logger.error(f"Timeout connecting to MCP server: {server_name}")
                return False
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")
                return False

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect from.
        """
        if server_name not in self._connections:
            return

        async with self._connection_locks.get(
            server_name, asyncio.Lock()
        ):
            if server_name not in self._connections:
                return

            conn = self._connections.pop(server_name)
            try:
                await conn.cleanup()
                logger.info(f"Disconnected from MCP server: {server_name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from {server_name}: {e}")

    async def close_all(self) -> None:
        """Disconnect from all MCP servers."""
        server_names = list(self._connections.keys())
        for name in server_names:
            await self.disconnect(name)
        logger.info("All MCP connections closed")

    async def _get_or_create_connection(
        self, server_name: str
    ) -> Optional[MCPServerConnection]:
        """Get existing connection or create a new one.

        Args:
            server_name: Name of the server.

        Returns:
            MCPServerConnection or None if connection failed.
        """
        if server_name not in self._connections:
            success = await self.connect(server_name)
            if not success:
                return None

        return self._connections.get(server_name)

    async def discover_tools(self, server_name: str) -> List[MCPTool]:
        """Discover tools from an MCP server.

        Args:
            server_name: Name of the MCP server.

        Returns:
            List of MCPTool objects discovered from the server.
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            logger.error(f"Cannot discover tools: not connected to {server_name}")
            return []

        try:
            tools_response = await conn.session.list_tools()
            tools = []
            for tool in tools_response.tools:
                tools.append(MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    server_name=server_name,
                ))
            logger.info(f"Discovered {len(tools)} tools from {server_name}")
            return tools
        except Exception as e:
            logger.error(f"Failed to discover tools from {server_name}: {e}")
            return []

    async def list_resources(self, server_name: str) -> List[MCPResource]:
        """List available resources from an MCP server.

        Args:
            server_name: Name of the MCP server.

        Returns:
            List of MCPResource objects.
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            logger.error(f"Cannot list resources: not connected to {server_name}")
            return []

        try:
            resources_response = await conn.session.list_resources()
            resources = []
            for resource in resources_response.resources:
                resources.append(MCPResource(
                    uri=str(resource.uri),
                    name=resource.name or str(resource.uri),
                    mime_type=resource.mimeType if hasattr(resource, 'mimeType') else "text/plain",
                    description=resource.description if hasattr(resource, 'description') else "",
                ))
            logger.info(f"Found {len(resources)} resources from {server_name}")
            return resources
        except Exception as e:
            logger.error(f"Failed to list resources from {server_name}: {e}")
            return []

    async def call_tool(
        self, 
        server_name: str, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> str:
        """Call a tool on an MCP server.

        Args:
            server_name: Name of the MCP server.
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            Tool execution result as a string.
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            return f"Error: Not connected to MCP server {server_name}"

        try:
            from mcp import types as mcp_types

            result = await conn.session.call_tool(tool_name, arguments=arguments)
            
            # Extract content from result
            contents = []
            for content in result.content:
                if isinstance(content, mcp_types.TextContent):
                    contents.append(content.text)
                elif hasattr(content, 'text'):
                    contents.append(content.text)
                elif hasattr(content, 'data'):
                    contents.append(f"[Binary data: {len(content.data)} bytes]")
                else:
                    contents.append(str(content))

            return "\n".join(contents)

        except Exception as e:
            error_msg = f"Error calling tool {tool_name}: {e}"
            logger.error(error_msg)
            return error_msg

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from an MCP server.

        Args:
            server_name: Name of the MCP server.
            uri: URI of the resource to read.

        Returns:
            Resource content as a string.
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            return f"Error: Not connected to MCP server {server_name}"

        try:
            from mcp import types as mcp_types

            result = await conn.session.read_resource(uri)
            
            contents = []
            for content in result.contents:
                if isinstance(content, mcp_types.TextContent):
                    contents.append(content.text)
                elif hasattr(content, 'text'):
                    contents.append(content.text)
                else:
                    contents.append(str(content))

            return "\n".join(contents)

        except Exception as e:
            error_msg = f"Error reading resource {uri}: {e}"
            logger.error(error_msg)
            return error_msg

    def get_tools_for_agent(self, agent_name: str) -> List[MCPTool]:
        """Get all tools from MCP servers enabled for an agent (sync wrapper).

        This is a synchronous wrapper that runs the async version.
        For new code, prefer using discover_tools() directly.

        Args:
            agent_name: Name of the agent.

        Returns:
            List of MCPTool objects.
        """
        servers = self.get_enabled_servers(agent_name)
        if not servers:
            return []

        async def _gather_tools():
            all_tools = []
            for server in servers:
                tools = await self.discover_tools(server.name)
                all_tools.extend(tools)
            return all_tools

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _gather_tools())
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(_gather_tools())
        except Exception as e:
            logger.warning(f"Failed to get tools for {agent_name}: {e}")
            return []

    def _load_config(self) -> Dict[str, Any]:
        """Load MCP configuration from YAML file.

        Returns:
            Configuration dictionary.
        """
        if not self.config_path.exists():
            logger.warning(f"MCP config not found: {self.config_path}")
            return {"servers": {}, "defaults": []}

        try:
            content = self.config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content)
            return self._expand_env_vars(config)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse MCP config: {e}")
            return {"servers": {}, "defaults": []}

    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand environment variables in config.

        Args:
            obj: Configuration object.

        Returns:
            Object with environment variables expanded.
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return pattern.sub(replace, obj)
        return obj


# Singleton instance
_default_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """Get the default MCPManager singleton.

    Returns:
        MCPManager instance.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = MCPManager()
    return _default_manager


def reset_mcp_manager() -> None:
    """Reset the MCPManager singleton.
    
    Useful for testing or when reconfiguration is needed.
    """
    global _default_manager
    if _default_manager is not None:
        # Try to cleanup connections
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                loop.run_until_complete(_default_manager.close_all())
        except Exception:
            pass
    _default_manager = None
