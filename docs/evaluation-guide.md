# Evaluation Guide

Create a versioned dataset with `POST /evaluations/datasets`, then request a run with
`POST /evaluations`. The request commits an `EVALUATION_REQUESTED` outbox event; the
worker executes cases and persists one idempotent result per run/case.

Run requests default to `SYSTEM`. SYSTEM datasets must not contain client-supplied
`actual_output`; each case validates `campaign_input`, creates evaluation-owned
campaign/workflow records, runs `CampaignWorkflow` and the Agentic runtime with the
deterministic mock provider, then collects persisted workflow, Agent, tool, policy,
action, retry, and error state. Use `SNAPSHOT` explicitly only for assertion-engine
tests or historical imports.

Deterministic assertions cover schema validity, required platforms/fields, workflow
status, policy decisions, and forbidden actions. Reports aggregate success, retry,
failure, timeout, manual-review, Agent behavior, quality, tokens, estimated cost, and
duration. The golden gate requires 100% schema validity, forbidden-action blocking,
and policy accuracy, plus configured success and LLM-call bounds.

Every run records dataset, model configuration hash, prompt, tool registry, policy,
and application versions. Never modify a historical dataset version or silently
update a baseline. Create a new version and review its regression result. CI executes
the eight-case `golden-m6` SYSTEM dataset and compares it with
`evaluation/baselines/golden-m6-v1.json`. Real-provider runs are outside this
deterministic release gate.
