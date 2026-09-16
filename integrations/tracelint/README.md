# tracelint integration (proof of concept)

[tracelint](https://github.com/AshwinUgale/tracelint) is a **deterministic, judge-free linter for
agent runs**. It reads an execution trace — what the agents *actually did* — and flags structural
defects with the exact evidence and a CI exit code. No second model judges the trace, so the same
input always produces the same finding.

This folder is a **self-contained PoC**: it shows tracelint catching real structural defects in a
DATAGEN research run, staying **conservative** where it cannot prove a failure, and staying **quiet**
on legitimate repeated research and retries. It changes **no runtime code** and adds **no CI
workflow** — wiring the CI gate is left to the maintainers.

## What's here

| File | Purpose |
|------|---------|
| `tools.json` | Tool contract **with** a `failure_when` predicate (the recommended contract). |
| `tools.no_contract.json` | The same contract **without** `failure_when`, for the comparison below. |
| `traces/research_run_defect.json` | A research run with two structural defects. |
| `traces/research_run_clean.json` | A legitimate run: different research reads + a retried scrape. |
| `capture_example.py` | Reference recipe for capturing a **real** DATAGEN run (not run in CI). |
| `../../tests/test_tracelint_integration.py` | Lints the traces and asserts the three cases below. |

## Why `failure_when` is the crux

DATAGEN's tools **catch exceptions and return an `"Error: ..."` string** rather than raising
(`src/tools/internet.py`, `src/tools/FileEdit.py`). A captured span for such a call therefore has no
raised exception and no error status — tracelint's OpenInference adapter maps it to **`UNKNOWN`**,
never `ok`/`error`. So tracelint cannot know an `"Error: ..."` string is a failure until the contract
says so. `tools.json` declares that with one predicate per tool:

```json
"failure_when": { "pointer": "", "matches": "^Error" }
```

(`pointer: ""` = the whole result; `matches` = a regex on it.) This is exactly the comparison this
PoC is meant to surface.

## The three cases it proves

**1. With the contract → defects are provable and gate CI (exit 2).** In `research_run_defect.json`
a `google_search` returned `"Error: RateLimited: ..."`, that string was written into the report via
the side-effecting `create_document` (**R2b, `hard_defect`**), and the non-idempotent `edit_document`
was then called **twice with identical arguments** (**R8**):

```
$ tracelint check integrations/tracelint/traces/research_run_defect.json \
    --tools integrations/tracelint/tools.json --rules R1,R2a,R2b,R4,R5,R6,R7,R8
datagen-research-defect: 3 finding(s), exit 2
  [hard_event]  R2a  'google_search' returned a declared failure ((result)='Error: RateLimited: ...')
  [hard_defect] R2b  value(s) from the errored 'google_search' result reused as arguments to
                     'create_document' (a side-effecting action, no fallback)
  [hard_event]  R8   'edit_document' repeats an equivalent non-idempotent side-effecting call
```

**2. Without the contract → tracelint stays conservative (exit 0).** Same trace, `tools.no_contract.json`:
the `"Error: ..."` results are structurally `UNKNOWN`, so tracelint reports only review-only
candidates (and discloses fail-closed suppressions for the side-effecting calls it could not verify)
rather than guessing — it does **not** gate CI:

```
$ tracelint check integrations/tracelint/traces/research_run_defect.json \
    --tools integrations/tracelint/tools.no_contract.json --rules R1,R2a,R2b,R4,R5,R6,R7,R8 --include-candidates
datagen-research-defect: 2 finding(s), exit 0
  [candidate] R2a  'google_search' result may be an error — matches an exception-like pattern ('Error')
  [candidate] R8   'edit_document' repeats a call — the first call's outcome is unknown (may be a retry)
  suppressed (3): side-effecting results with no failure_when — cannot verify they did not fail
```

**3. Legitimate repetition is NOT flagged (exit 0).** `research_run_clean.json` has different research
reads (`google_search`, `arxiv`, `wikipedia`) and a scrape that fails once then **succeeds on retry**.
The transient error is surfaced as an *event*, not a *defect*:

```
$ tracelint check integrations/tracelint/traces/research_run_clean.json \
    --tools integrations/tracelint/tools.json --rules R1,R2a,R2b,R4,R5,R6,R7,R8
datagen-research-clean: 1 finding(s), exit 0
  [hard_event] R2a  'scrape_webpages' returned a declared failure ((result)='Error: Timeout')
```

Note the tiering: `hard_event` = *an error occurred*; `hard_defect` = *the agent structurally
mishandled it*. Only `hard_defect` fails CI (exit `2`), so a retried transient error stays green.

## Contract details, and why

- **Idempotency.** `create_document` opens its target with `"w"` and overwrites, so an identical
  repeat leaves the same state — it is declared `idempotent`, and a duplicate is **not** an R8
  defect. `edit_document` *inserts* lines, so a repeat changes the file — it is the genuinely
  non-idempotent tool and is the R8 case here.
- **Read-only tools.** `google_search`, `scrape_webpages`, `wikipedia`, `arxiv`, `collect_data`,
  `read_document`, and `list_directory` are declared non-side-effecting (so R7 doesn't flag the ones
  agents actually use, like `wikipedia` / `arxiv`).
- **Rules.** Runs every shipped rule except R3 — i.e. `R1,R2a,R2b,R4,R5,R6,R7,R8`, matching the test
  (`default_rules()` minus R3). R1 (schema) is included but auto-suppresses without tool schemas
  (disclosed, never a pass); R3 (hallucinated-arg) needs `x-value-origin` provenance annotations and
  is scoped out rather than flag every model-generated search query.

## Run it

```bash
pip install "tracelint>=0.8.0"                  # the version this PoC was verified against
pytest tests/test_tracelint_integration.py      # skips cleanly if tracelint isn't installed
```

## Capturing a real run

The committed traces are hand-written to DATAGEN's real result shapes. To lint an **actual** run,
capture one and lint it — see [`capture_example.py`](capture_example.py), which mirrors
`MultiAgentSystem.run` (`src/system.py`):

```bash
pip install "tracelint[capture-langchain]>=0.8.0"   # LangChain instrumentor; also captures LangGraph
# around graph.stream(create_initial_state(topic), ...):  with capture("datagen_run.json", framework="langgraph"): ...
tracelint check datagen_run.json --format openinference \
  --tools integrations/tracelint/tools.json --rules R1,R2a,R2b,R4,R5,R6,R7,R8
```

A full run is interactive (`src/system.py` reads the topic via `input()`). DATAGEN runs on LangGraph,
so `framework="langgraph"` is used (it wraps the same LangChain OpenInference instrumentor).
