# Evaluation Guide

Create a versioned dataset with `POST /evaluations/datasets`, then request a run with
`POST /evaluations`. The request commits an `EVALUATION_REQUESTED` outbox event; the
worker executes cases and persists one idempotent result per run/case.

Deterministic assertions cover schema validity, required platforms/fields, workflow
status, policy decisions, and forbidden actions. Reports aggregate success, retry,
failure, timeout, manual-review, Agent behavior, quality, tokens, estimated cost, and
duration. The golden gate requires 100% schema validity, forbidden-action blocking,
and policy accuracy, plus configured success and LLM-call bounds.

Every run records dataset, model configuration hash, prompt, tool registry, policy,
and application versions. Never modify a historical dataset version or silently
update a baseline. Create a new version and review its regression result. Real-provider
runs are manual; default CI uses deterministic fixtures and the mock provider.
