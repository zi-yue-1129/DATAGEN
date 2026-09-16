"""Proof of concept: lint representative DATAGEN research traces with tracelint.

tracelint (https://github.com/AshwinUgale/tracelint) is a deterministic, judge-free linter for
agent runs. It reads an execution trace and flags structural defects — ignored tool errors,
errored values reused in side effects, loops, duplicate side effects — with the exact evidence and
a CI exit code; no model judges the trace.

The traces under ``integrations/tracelint/`` mirror DATAGEN's real tool-calling flow. DATAGEN tools
catch exceptions and *return* ``"Error: ..."`` strings rather than raising, so a captured result
carries no structured error status. These tests therefore show three things:

* with a ``failure_when`` contract (``tools.json``), a run with real structural defects is caught
  and would gate CI (exit code 2);
* without that contract (``tools.no_contract.json``), the same errored strings are structurally
  UNKNOWN, so tracelint stays conservative and does not gate CI (exit code 0); and
* a legitimate run — different research reads plus a retried scrape — is not flagged as a defect.

tracelint is an optional dev dependency; the test skips cleanly when it is absent, so it never
affects DATAGEN's own test run or CI. To run it: ``pip install "tracelint>=0.8.0"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

tracelint = pytest.importorskip("tracelint", minversion="0.8.0")

_INTEGRATION = Path(__file__).resolve().parents[1] / "integrations" / "tracelint"
_TRACES = _INTEGRATION / "traces"
_CONTRACT = _INTEGRATION / "tools.json"
_NO_CONTRACT = _INTEGRATION / "tools.no_contract.json"


def _lint(trace_name: str, tools_path: Path) -> Any:
    """Lint one trace fixture against a tools contract.

    Args:
        trace_name: File name of the trace under ``integrations/tracelint/traces``.
        tools_path: Path to the ``tools.json`` contract to load.

    Returns:
        The tracelint report for the run.
    """
    trace = tracelint.Trace.load(str(_TRACES / trace_name))
    registry = tracelint.ToolRegistry.load(str(tools_path))
    # Every shipped rule except R3 (hallucinated argument), which needs per-field provenance
    # annotations (x-value-origin) to be meaningful and would otherwise flag every
    # model-generated search query.
    rules = [rule for rule in tracelint.default_rules() if rule.id != "R3"]
    return tracelint.lint_trace(trace, rules, registry)


def _hard_defect_rules(report: Any) -> set[str]:
    """Return the rule ids that produced a hard-defect finding in ``report``."""
    tier = tracelint.ConfidenceTier.HARD_DEFECT
    return {finding.rule for finding in report.active_findings if finding.tier is tier}


def test_defect_trace_is_caught_with_a_failure_contract() -> None:
    """With a failure_when contract, the run's defects are provable and gate CI (exit 2).

    An errored ``google_search`` string was written into the report via the side-effecting
    ``create_document`` (R2b), and the non-idempotent ``edit_document`` was repeated verbatim (R8).
    """
    report = _lint("research_run_defect.json", _CONTRACT)

    assert report.has_hard_defect
    assert report.exit_code == 2
    assert "R2b" in _hard_defect_rules(report)
    assert "R8" in {finding.rule for finding in report.active_findings}


def test_defect_trace_stays_conservative_without_a_contract() -> None:
    """Without failure_when, DATAGEN's ``"Error: ..."`` results are structurally UNKNOWN.

    tracelint then reports only review-only candidates and does not gate CI (exit 0), instead of
    guessing that an unclassifiable result was a failure.
    """
    report = _lint("research_run_defect.json", _NO_CONTRACT)

    assert not report.has_hard_defect
    assert report.exit_code == 0


def test_clean_trace_tolerates_legit_repeats_and_retries() -> None:
    """Different research reads and a retried scrape are legitimate, so a clean run stays green.

    The transient scrape error is surfaced as an event, never a defect, so exit code stays 0.
    """
    report = _lint("research_run_clean.json", _CONTRACT)

    assert not report.has_hard_defect
    assert report.exit_code == 0
    assert not _hard_defect_rules(report)
