# gebra integration (PoC)

A design-time check of DATAGEN's workflow graph: every automatic loop names the bound that ends it.

[gebra](https://github.com/Gebra-Tech/gebra#readme) imports a LangGraph graph and reads its wiring without running it: it never invokes a node, router, tool or model, and opens no connection. Its P-02 termination-witness check fails with `cycle-without-termination-witness` (FATAL, DEFENSIBLE) when a cycle passes through no node declaring a loop variant, and names the nodes involved. tracelint (`integrations/tracelint/`) checks traces of runs that happened; this checks the graph as defined.

## What is declared

`gebra.toml` declares `step_count` on two nodes:

- **Process**: the self-loop and the Process → worker → QualityReview → NoteTaker laps end once `step_count > 20` (`process_router`).
- **QualityReview**: the four worker ↔ QualityReview revision loops end once `step_count > 20` or `revision_count > 3` (`QualityReview_router`).

The declarations are trusted, not checked against the node or router code: a pass means every loop names a declared bound, not that a run finishes or that the code enforces the bound.

## What it doesn't see

- Whether the node and router code enforces a declaration. The entries are trusted, not checked against that code, so the check does not verify the termination logic itself.
- HumanChoice ↔ Hypothesis (regenerate the hypothesis) has no counter; the person ends it. The test pins it as the only undeclared loop.
- The Refiner → HumanReview → Process lap counts as declared because it passes through Process, though a "no" at HumanReview ends it.
- Each agent's own `create_agent` loop (model ↔ tools) runs inside a node, bounded by the `recursion_limit` passed at invoke (`max_iterations`); gebra 0.1.1 cannot declare that limit.

## Run it

```bash
pip install "gebra>=0.1.1,<0.2"
pytest tests/test_gebra_loop_bounds.py
```

Without gebra installed the tests are skipped, as `tests/test_tracelint_integration.py` is without tracelint. Installing gebra also registers its pytest plugin (`--gebra-*` options, markers and `gebra_*` fixtures); these tests call its API directly and use none of them.
