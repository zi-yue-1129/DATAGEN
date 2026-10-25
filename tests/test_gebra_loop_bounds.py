"""Every automatic loop in the workflow graph declares the bound that ends it.

integrations/gebra/gebra.toml names the state key that bounds the Process and
QualityReview loops (step_count) and the comparison that ends them. gebra reads
the graph's wiring without running it, and fails when a cycle passes through no
declared node. The declarations are trusted, not checked against the node or
router code. The one loop left undeclared is HumanChoice <-> Hypothesis, which
the person at HumanChoice ends; any other undeclared loop fails the first test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.core.workflow import WorkflowManager

gebra = pytest.importorskip("gebra", minversion="0.1.1")
verify = pytest.importorskip("gebra.verify").verify

SIDECAR = Path(__file__).resolve().parents[1] / "integrations" / "gebra" / "gebra.toml"
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
HUMAN_ENDED_LOOP = ["HumanChoice", "Hypothesis"]


def _workflow() -> Any:
    """Wire the workflow graph with placeholder agents.

    Returns:
        The StateGraph that WorkflowManager.setup_workflow() wires.
    """
    manager = WorkflowManager.__new__(WorkflowManager)
    manager.agents = {name: object() for name in AGENT_NAMES}
    manager.setup_workflow()
    return manager.workflow


def _loops(sidecar: Path, workflow: Any = None) -> Any:
    """Check a workflow graph's loops against a gebra.toml.

    Args:
        sidecar: The gebra.toml that declares the loop bounds.
        workflow: The StateGraph to check; DATAGEN's own graph when None.

    Returns:
        gebra's termination-witness outcome.
    """
    graph = (_workflow() if workflow is None else workflow).compile()
    envelope = gebra.extract(graph, sidecar=str(sidecar))
    return verify(envelope.ir).outcome_for("termination-witness")


def test_every_automatic_loop_declares_its_bound() -> None:
    """The only loop without a declared bound is the one a person ends."""
    loops = _loops(SIDECAR)

    assert loops.result == "fail"
    assert sorted(loops.failure.location.nodes) == HUMAN_ENDED_LOOP
    assert not loops.failure.co_failures


def test_a_new_loop_without_a_declared_bound_is_reported() -> None:
    """A retry route that sends Search back to itself, with no counter, is reported."""
    workflow = _workflow()
    # gebra reads the route's targets; it never calls the router.
    workflow.add_conditional_edges(
        "Search",
        lambda state: "QualityReview",
        {"Search": "Search", "QualityReview": "QualityReview"},
    )

    loops = _loops(SIDECAR, workflow)

    assert sorted(loops.failure.location.nodes) == HUMAN_ENDED_LOOP
    assert [sorted(other.location.nodes) for other in loops.failure.co_failures] == [
        ["Search"]
    ]


def test_an_undeclared_revision_loop_is_reported(tmp_path: Path) -> None:
    """Without the QualityReview entry, the worker <-> QualityReview loops are reported."""
    text = SIDECAR.read_text(encoding="utf-8")
    only_process = tmp_path / "gebra.toml"
    only_process.write_text(
        text[: text.index("[nodes.QualityReview]")], encoding="utf-8"
    )

    loops = _loops(only_process)

    assert sorted(loops.failure.location.nodes) == [
        "Coder",
        "QualityReview",
        "Report",
        "Search",
        "Visualization",
    ]
