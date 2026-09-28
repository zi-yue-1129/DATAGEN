"""Failed agent runs count toward the step limit (#59).

agent_node's error path returned no step_count, so an agent that kept failing
was never counted: a failing Process routed back to itself, and a failing
QualityReview kept sending the worker back for a revision, until LangGraph's
recursion limit ended the run with GraphRecursionError.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.base import BaseAgent
from src.core.node import agent_node
from src.core.router import QualityReview_router
from src.core.state import State, create_initial_state
from src.core.workflow import WorkflowManager

AGENT_NAMES = [
    "hypothesis_agent",
    "process_agent",
    "visualization_agent",
    "code_agent",
    "search_agent",
    "report_agent",
    "quality_review_agent",
    "note_agent",
    "refiner_agent",
]


class StubAgent:
    """Answers with a message named after the agent, or raises after fail_after calls."""

    def __init__(
        self,
        name: str,
        calls: Counter[str],
        fail_after: int | None = None,
        updates: dict[str, Any] | None = None,
    ) -> None:
        """Initializes the stub.

        Args:
            name: The agent name, used for its message and its call count.
            calls: The call counter shared by the stubs of one run.
            fail_after: Raise on every call after this many; None never raises.
            updates: The state updates returned after a successful call.
        """
        self.name = name
        self.calls = calls
        self.fail_after = fail_after
        self.updates = updates or {}

    def invoke(self, state: Any) -> dict[str, Any]:
        """Counts the call, then answers or raises like a failed model call.

        Args:
            state: The workflow state (unused).

        Returns:
            A result with one message named after the agent.

        Raises:
            RuntimeError: On every call after ``fail_after`` calls.
        """
        self.calls[self.name] += 1
        if self.fail_after is not None and self.calls[self.name] > self.fail_after:
            raise RuntimeError("model call failed")
        return {"messages": [AIMessage(content=self.name, name=self.name)]}

    def get_state_updates(self, state: Any, output: Any) -> dict[str, Any]:
        """Returns the scripted updates, as a real agent's StateUpdater hook does.

        Args:
            state: The workflow state (unused).
            output: The agent's output (unused).

        Returns:
            A copy of the scripted updates.
        """
        return dict(self.updates)


def _run_workflow(
    agents: dict[str, StubAgent], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Runs the real workflow graph with stub agents; the human continues, then ends.

    Args:
        agents: The stub agents, keyed like WorkflowManager.create_agents().
        monkeypatch: Used to answer the human nodes' input() prompts.

    Returns:
        The final workflow state.
    """
    answers = iter(["2", "no"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    manager = WorkflowManager.__new__(WorkflowManager)
    manager.agents = agents
    manager.setup_workflow()
    assert manager.graph is not None
    result: dict[str, Any] = manager.graph.invoke(
        create_initial_state("topic"), {"recursion_limit": 100}
    )
    return result


def test_failed_agent_run_counts_as_a_step() -> None:
    """agent_node's error path advances step_count like a successful run."""
    calls: Counter[str] = Counter()
    state = State(messages=[HumanMessage(content="topic")], step_count=3)
    agent = cast(BaseAgent, StubAgent("process_agent", calls, fail_after=0))

    updates = agent_node(state, agent, "process_agent")

    assert updates["step_count"] == 4
    assert updates["messages"][-1].content == "Error: model call failed"


def test_quality_review_router_applies_step_limit_to_revisions() -> None:
    """A revision requested past the step limit goes to NoteTaker."""
    messages = [
        HumanMessage(content="topic"),
        AIMessage(content="results", name="search_agent"),
        AIMessage(content="Error: model call failed", name="quality_review_agent"),
    ]
    state = State(
        messages=messages,
        needs_revision=True,
        revision_count=1,
        step_count=21,
    )

    assert QualityReview_router(state) == "NoteTaker"


def test_failing_process_agent_ends_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Process agent that always fails reaches Refiner instead of looping."""
    calls: Counter[str] = Counter()
    agents = {name: StubAgent(name, calls) for name in AGENT_NAMES}
    agents["process_agent"] = StubAgent("process_agent", calls, fail_after=0)

    result = _run_workflow(agents, monkeypatch)

    # Twenty failed runs take step_count from 1 to 21, past the limit of 20.
    assert calls["process_agent"] == 20
    assert calls["refiner_agent"] == 1
    assert result["step_count"] == 21


def test_failing_quality_review_ends_the_revision_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reviewer that asks for a revision and then keeps failing stops at the step limit."""
    calls: Counter[str] = Counter()
    agents = {name: StubAgent(name, calls) for name in AGENT_NAMES}
    agents["process_agent"] = StubAgent(
        "process_agent", calls, updates={"next_workflow_step": "Search"}
    )
    agents["quality_review_agent"] = StubAgent(
        "quality_review_agent",
        calls,
        fail_after=1,
        updates={"needs_revision": True, "revision_count": 1},
    )

    _run_workflow(agents, monkeypatch)

    # Each Search and review pair adds two steps; pair ten passes the limit of 20.
    assert calls["search_agent"] == 10
    assert calls["quality_review_agent"] == 10
    assert calls["refiner_agent"] == 1
