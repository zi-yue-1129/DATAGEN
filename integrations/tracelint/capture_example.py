"""Capture a REAL DATAGEN run into a lintable trace (reference — not run in CI).

The committed fixtures under ``traces/`` are hand-written to DATAGEN's real result shapes so the
PoC is deterministic and offline. This script shows the other half: recording an actual DATAGEN
graph run and linting it, with no changes to DATAGEN's runtime.

    pip install "tracelint[capture-langchain]>=0.8.0"   # LangChain instrumentor; also captures LangGraph
    python integrations/tracelint/capture_example.py     # run from the repo root

``tracelint.capture`` stands the framework's stock OpenInference instrumentor up against a *local*
OTel provider whose only exporter writes the flat OpenInference span shape to a file, so any tracing
you already run is left untouched and the file lints with ``--format openinference``.

Note: a full DATAGEN run is interactive — ``src/system.py`` reads the topic via ``input()`` — so run
this from a terminal. The mechanism mirrors ``MultiAgentSystem.run`` in ``src/system.py``.
"""

from __future__ import annotations

from pathlib import Path

_OUT = Path("datagen_run.json")
_TOOLS = Path(__file__).with_name("tools.json")


def main() -> None:
    """Capture one DATAGEN graph run and print how to lint it."""
    from tracelint.capture import capture

    from src import config
    from src.core.language_models import LanguageModelManager
    from src.core.state import create_initial_state
    from src.core.workflow import WorkflowManager

    # Build the graph the way MultiAgentSystem does (see src/system.py).
    manager = WorkflowManager(
        lm_manager=LanguageModelManager(),
        working_directory=config.WORKING_DIRECTORY,
    )
    graph = manager.get_graph()
    user_input = input("Please enter your research topic: ")

    # framework="langgraph" wraps the LangChain OpenInference instrumentor DATAGEN's graph uses.
    with capture(str(_OUT), framework="langgraph"):
        for _event in graph.stream(
            create_initial_state(user_input),
            {"configurable": {"thread_id": "1"}, "recursion_limit": 3000},
            stream_mode="values",
        ):
            pass

    print(
        f"Captured {_OUT}. Lint it with:\n"
        f"  tracelint check {_OUT} --format openinference "
        f"--tools {_TOOLS} --rules R1,R2a,R2b,R4,R5,R6,R7,R8"
    )


if __name__ == "__main__":
    main()
