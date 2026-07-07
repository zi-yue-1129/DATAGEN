"""Regression tests for LangGraph state and workflow routing."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

CORE_PACKAGE_NAME = "_datagen_core_under_test"
CORE_DIRECTORY = Path(__file__).resolve().parents[1] / "src" / "core"

core_package = types.ModuleType(CORE_PACKAGE_NAME)
core_package.__path__ = [str(CORE_DIRECTORY)]
sys.modules[CORE_PACKAGE_NAME] = core_package


def _load_core_module(module_name: str) -> ModuleType:
    """Load a core module without triggering src.core package side effects."""
    module_path = CORE_DIRECTORY / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"{CORE_PACKAGE_NAME}.{module_name}", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


state_module = _load_core_module("state")
router_module = _load_core_module("router")
State = state_module.State
process_router = router_module.process_router


def test_state_messages_use_append_reducer() -> None:
    """State.messages should append node messages instead of overwriting history."""

    def review_node(state: Any) -> dict[str, list[BaseMessage]]:
        """Return only the new message produced by a human review node."""
        return {"messages": [HumanMessage(content="review request")]}

    graph = StateGraph(State)
    graph.add_node("review", review_node)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)

    result: dict[str, Any] = graph.compile().invoke(
        {"messages": [HumanMessage(content="original request")]}
    )

    assert [message.content for message in result["messages"]] == [
        "original request",
        "review request",
    ]


def test_process_router_applies_step_limit_before_valid_agent_route() -> None:
    """process_router should stop long cycles before following valid agent routes."""
    state = State(next_workflow_step="Coder", step_count=21)

    assert process_router(state) == "Refiner"
