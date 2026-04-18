"""LangChain tool adapters for MCP (Model Context Protocol) tools.

This module provides adapters that wrap MCP tools as LangChain tools,
enabling seamless integration between MCP servers and LangChain agents.

Example:
    from src.tools.mcp_tools import create_mcp_tool_adapters
    from src.core.mcp_manager import get_mcp_manager
    
    manager = get_mcp_manager()
    mcp_tools = await manager.discover_tools("filesystem")
    langchain_tools = create_mcp_tool_adapters(mcp_tools, "filesystem")
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from ..logger import setup_logger


logger = setup_logger()


def _create_args_schema(
    tool_name: str, 
    input_schema: Dict[str, Any]
) -> Type[BaseModel]:
    """Create a Pydantic model from JSON schema for tool arguments.

    Args:
        tool_name: Name of the tool (used for model naming).
        input_schema: JSON schema for the tool's input.

    Returns:
        A Pydantic BaseModel class representing the schema.
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    field_definitions = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")
        default = ... if prop_name in required else None

        # Map JSON schema types to Python types
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        python_type = type_mapping.get(prop_type, str)

        # Handle optional types
        if prop_name not in required:
            python_type = Optional[python_type]

        field_definitions[prop_name] = (
            python_type,
            Field(default=default, description=description)
        )

    # Create a dynamic Pydantic model
    model_name = f"{tool_name.replace('-', '_').title()}Args"
    if not field_definitions:
        # Empty schema - create a simple model
        return create_model(model_name)
    
    return create_model(model_name, **field_definitions)


class MCPToolAdapter(BaseTool):
    """Adapter that wraps an MCP tool as a LangChain tool.

    This adapter handles the translation between LangChain's tool interface
    and MCP's tool calling protocol.

    Attributes:
        name: Tool name.
        description: Tool description.
        mcp_server: Name of the MCP server providing this tool.
        mcp_tool_name: Original tool name on the MCP server.
        args_schema: Pydantic model for argument validation.
    """

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    mcp_server: str = Field(..., description="MCP server name")
    mcp_tool_name: str = Field(..., description="Original MCP tool name")
    args_schema: Type[BaseModel] = Field(..., description="Arguments schema")

    def _run(self, **kwargs: Any) -> str:
        """Synchronous execution - wraps async call.

        Args:
            **kwargs: Tool arguments.

        Returns:
            Tool execution result as string.
        """
        try:
            from ..core.mcp_manager import get_mcp_manager
            manager = get_mcp_manager()
            
            if manager._main_loop and manager._main_loop.is_running():
                # Use the dedicated background loop
                def _run_async():
                    return asyncio.run_coroutine_threadsafe(self._arun(**kwargs), manager._main_loop).result(timeout=120)
                
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(_run_async).result()

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # If we're already in a running event loop, we must run the
                # async tool call in a separate thread to avoid nested loops.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        self._arun(**kwargs)
                    )
                    return future.result(timeout=120)
            else:
                # No running event loop in this thread, safe to use asyncio.run
                return asyncio.run(self._arun(**kwargs))
        except Exception as e:
            error_msg = f"Error executing MCP tool {self.name}: {e}"
            logger.error(error_msg)
            return error_msg

    async def _arun(self, **kwargs: Any) -> str:
        """Asynchronous execution via MCP manager.

        Args:
            **kwargs: Tool arguments.

        Returns:
            Tool execution result as string.
        """
        from ..core.mcp_manager import get_mcp_manager

        manager = get_mcp_manager()
        result = await manager.call_tool(
            self.mcp_server,
            self.mcp_tool_name,
            kwargs
        )
        return result


def create_mcp_tool_adapter(
    tool_name: str,
    tool_description: str,
    input_schema: Dict[str, Any],
    server_name: str,
) -> MCPToolAdapter:
    """Create a LangChain tool adapter from MCP tool info.

    Args:
        tool_name: Name of the MCP tool.
        tool_description: Description of the tool.
        input_schema: JSON schema for tool input.
        server_name: Name of the MCP server.

    Returns:
        MCPToolAdapter instance.
    """
    args_schema = _create_args_schema(tool_name, input_schema)

    # Create a prefixed name to avoid conflicts
    prefixed_name = f"mcp_{server_name}_{tool_name}"

    return MCPToolAdapter(
        name=prefixed_name,
        description=f"[MCP:{server_name}] {tool_description}",
        mcp_server=server_name,
        mcp_tool_name=tool_name,
        args_schema=args_schema,
    )


def create_mcp_tool_adapters(
    mcp_tools: List[Any],
    server_name: str,
) -> List[MCPToolAdapter]:
    """Create LangChain tool adapters from a list of MCP tools.

    Args:
        mcp_tools: List of MCPTool objects.
        server_name: Name of the MCP server.

    Returns:
        List of MCPToolAdapter instances.
    """
    adapters = []
    for tool in mcp_tools:
        try:
            adapter = create_mcp_tool_adapter(
                tool_name=tool.name,
                tool_description=tool.description,
                input_schema=tool.input_schema,
                server_name=server_name,
            )
            adapters.append(adapter)
            logger.debug(f"Created adapter for MCP tool: {tool.name}")
        except Exception as e:
            logger.warning(f"Failed to create adapter for {tool.name}: {e}")

    return adapters


async def get_mcp_tools_async(server_names: List[str]) -> List[MCPToolAdapter]:
    """Asynchronously get LangChain tools from MCP servers.

    Args:
        server_names: List of MCP server names to get tools from.

    Returns:
        List of MCPToolAdapter instances.
    """
    from ..core.mcp_manager import get_mcp_manager

    manager = get_mcp_manager()
    all_tools = []

    for server_name in server_names:
        try:
            mcp_tools = await manager.discover_tools(server_name)
            adapters = create_mcp_tool_adapters(mcp_tools, server_name)
            all_tools.extend(adapters)
            logger.info(
                f"Loaded {len(adapters)} tools from MCP server: {server_name}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to load tools from {server_name}: {e}"
            )

    return all_tools


def get_mcp_tools_sync(server_names: List[str]) -> List[MCPToolAdapter]:
    """Synchronously get LangChain tools from MCP servers.

    This is a convenience wrapper for sync contexts.

    Args:
        server_names: List of MCP server names to get tools from.

    Returns:
        List of MCPToolAdapter instances.
    """
    try:
        from ..core.mcp_manager import get_mcp_manager
        manager = get_mcp_manager()
        
        if manager._main_loop and manager._main_loop.is_running():
            def _get_async():
                return asyncio.run_coroutine_threadsafe(get_mcp_tools_async(server_names), manager._main_loop).result(timeout=120)
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(_get_async).result()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    get_mcp_tools_async(server_names)
                )
                return future.result(timeout=120)
        else:
            return asyncio.run(get_mcp_tools_async(server_names))
    except Exception as e:
        logger.error(f"Failed to get MCP tools: {e}")
        return []
