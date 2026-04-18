from __future__ import annotations
import logging
import asyncio
import os
import yaml
import re
import anyio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

"""This module provides management of MCP server connections and tool exposure
for agents. It uses the official MCP Python SDK for real server communication
via stdio transport.

Reference: https://modelcontextprotocol.io/
"""


from ..logger import setup_logger


logger = setup_logger()
# Silence noisy system loggers
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("anyio").setLevel(logging.CRITICAL)


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
        client_context: Context manager for the transport (e.g. stdio).
        session_context: Context manager for the session.
        loop: The event loop this connection belongs to.
    """
    name: str
    session: Any  # mcp.ClientSession
    client_context: Any  # Context manager for the transport
    session_context: Any  # Context manager for the session
    loop: Any = None  # The event loop this connection belongs to


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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            config_path = os.path.join(config_dir, "mcp.yaml")
            
        self.config_path = Path(config_path)
        self._config: Optional[Dict[str, Any]] = None
        self._servers: Dict[str, MCPServerConfig] = {}
        self._connections: Dict[str, MCPServerConnection] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._mcp_stderr_file = None
        
        # Setup a loop exception handler to swallow noisy anyio/asyncio errors
        try:
            loop = asyncio.get_event_loop()
            def silent_exception_handler(loop, context):
                msg = context.get("message", "")
                if "asynchronous generator" in msg or "cancel scope" in msg:
                    return
                loop.default_exception_handler(context)
            loop.set_exception_handler(silent_exception_handler)
        except Exception:
            pass

    def _get_lock(self, server_name: str) -> asyncio.Lock:
        """Get or create a lock for a specific server."""
        if server_name not in self._connection_locks:
            self._connection_locks[server_name] = asyncio.Lock()
        return self._connection_locks[server_name]

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
        """Connect to an MCP server with locking."""
        async with self._get_lock(server_name):
            # Check if already connected and active
            if server_name in self._connections:
                conn = self._connections[server_name]
                if conn.session:
                    return True
                else:
                    # Clean up broken connection
                    await self._close_server_connection(server_name)

            config = self.get_server_config(server_name)
            if not config:
                logger.error(f"Configuration not found for MCP server: {server_name}")
                return False

            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                env = os.environ.copy()
                for key, value in config.env.items():
                    env[key] = value

                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=env
                )

                logger.info(f"Connecting to MCP server: {server_name}...")
                
                # Redirect stderr to avoid console noise from MCP servers
                if self._mcp_stderr_file is None:
                    try:
                        # Ensure logs directory exists
                        os.makedirs("logs", exist_ok=True)
                        self._mcp_stderr_file = open("logs/mcp_servers.log", "a", encoding="utf-8")
                    except Exception:
                        self._mcp_stderr_file = sys.stderr

                # Use a context manager but handle it manually to keep streams alive
                client_context = stdio_client(server_params, errlog=self._mcp_stderr_file)
                read_stream, write_stream = await client_context.__aenter__()
                
                session_context = ClientSession(read_stream, write_stream)
                session = await session_context.__aenter__()
                await session.initialize()

                self._connections[server_name] = MCPServerConnection(
                    name=server_name,
                    client_context=client_context,
                    session_context=session_context,
                    session=session,
                    loop=asyncio.get_running_loop()
                )
                logger.info(f"Successfully connected to {server_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to {server_name}: {str(e)}", exc_info=True)
                return False

    async def _close_server_connection(self, server_name: str) -> None:
        """Internal helper to close a connection cleanly."""
        conn = self._connections.pop(server_name, None)
        if conn:
            try:
                # Attempt graceful closure of the session and client contexts.
                # Catching anyio-specific task mismatch or closed resource errors 
                # that occur when loops are switched or tasks are terminated abruptly.
                if conn.session_context:
                    try:
                        await conn.session_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        logger.debug(f"Non-fatal error closing session context for {server_name}: {e}")
                
                if conn.client_context:
                    try:
                        await conn.client_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        logger.debug(f"Non-fatal error closing client context for {server_name}: {e}")
            except Exception as e:
                logger.debug(f"Error during cleanup of {server_name}: {e}")

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect from.
        """
        async with self._get_lock(server_name):
            await self._close_server_connection(server_name)
            logger.info(f"Disconnected from MCP server: {server_name}")

    async def close_all(self) -> None:
        """Disconnect from all MCP servers."""
        server_names = list(self._connections.keys())
        for name in server_names:
            await self.disconnect(name)
        logger.info("All MCP connections closed")

    async def _get_or_create_connection(
        self, server_name: str
    ) -> Optional[MCPServerConnection]:
        """Get existing connection or create a new one with loop-awareness."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if server_name in self._connections:
            conn = self._connections[server_name]
            # Verify if connection is valid for current loop
            if conn.loop is current_loop and conn.session:
                return conn
            else:
                logger.debug(f"Detected stale or loop-mismatched connection for {server_name}. Reconnecting...")
                await self.disconnect(server_name)

        success = await self.connect(server_name)
        if not success:
            return None

        return self._connections.get(server_name)

    async def discover_tools(self, server_name: str) -> List[MCPTool]:
        """Discover tools from an MCP server with robust retry.

        Args:
            server_name: Name of the MCP server.

        Returns:
            List of MCPTool objects discovered from the server.
        """
        for attempt in range(2):
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
                logger.warning(f"Failed to discover tools from {server_name} (attempt {attempt+1}/2): {e}")
                # Force disconnect before retry
                await self.disconnect(server_name)
                if attempt == 1:
                    logger.error(f"Max retries reached for tool discovery on {server_name}")
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

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """Call a tool on a server with robust retry and session validation."""
        if arguments is None:
            arguments = {}

        for attempt in range(3):
            try:
                # Use the loop-aware connection getter to ensure we are using 
                # a connection bound to the current event loop.
                conn = await self._get_or_create_connection(server_name)
                if not conn or not conn.session:
                    raise Exception(f"Failed to establish or retrieve valid connection for {server_name}")

                # Call the tool
                from mcp import types as mcp_types
                result = await conn.session.call_tool(tool_name, arguments)

                # Extract content from result
                contents = []
                for content in result.content:
                    text = ""
                    if isinstance(content, mcp_types.TextContent):
                        text = content.text
                    elif hasattr(content, 'text'):
                        text = content.text
                    elif hasattr(content, 'data'):
                        contents.append(f"[Binary data: {len(content.data)} bytes]")
                        continue
                    else:
                        text = str(content)
                    
                    # Filter out common MCP startup banners that sometimes leak into stdout
                    if "Secure MCP Filesystem Server running on stdio" in text:
                        continue
                    if "Client does not support MCP Roots" in text:
                        continue
                    
                    if text:
                        contents.append(text)

                return "\n".join(contents)

            except Exception as e:
                error_msg = str(e) or e.__class__.__name__
                logger.warning(f"Tool call failed (attempt {attempt+1}/3) for {server_name}.{tool_name}: {error_msg}")
                if attempt < 2:
                    # Force disconnect and clear session before retry
                    await self.disconnect(server_name)
                    # Use a slightly longer backoff for filesystem to allow OS resource cleanup
                    backoff = 1.0 if server_name != "filesystem" else 1.5
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Max retries reached for tool {tool_name} on {server_name}")
                    raise e

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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if self._main_loop and self._main_loop.is_running():
                # Use the dedicated background loop
                from concurrent.futures import Future
                def _run():
                    return asyncio.run_coroutine_threadsafe(_gather_tools(), self._main_loop).result(timeout=60)
                
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(_run).result()
            
            if loop and loop.is_running():
                # We're in an async context, create a new task in a separate thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _gather_tools())
                    return future.result(timeout=60)
            else:
                return asyncio.run(_gather_tools())
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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
                
            if loop and not loop.is_running():
                loop.run_until_complete(_default_manager.close_all())
            elif not loop:
                asyncio.run(_default_manager.close_all())
        except Exception:
            pass
    _default_manager = None
