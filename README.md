# Cyber Legends AI Workflow Backend

Production-oriented FastAPI backend with a deterministic campaign workflow and a
bounded, observable Agentic Core. The application remains authoritative for workflow
state, retries, approval decisions, persistence, authorization, and audit history.

## Architecture

```text
FastAPI Router
-> Application Service
-> Deterministic Workflow
-> Agentic Orchestrator
-> Specialist Agent
-> Bounded Agent Loop
-> Read-only Tools
-> Application Service
-> Repository
-> PostgreSQL
```

The three M4 specialists are `BRIEF_ANALYST`, `CONTENT_GENERATOR`, and
`CONTENT_REVIEWER`. Agents acquire bounded context, may request only their allowlisted
read-only tools, and return validated `BriefAnalysis`, `GeneratedContent`, or
`QualityReview` objects. Agents do not control workflow states, approve campaigns, or
publish content; the deterministic workflow interprets reviewer recommendations and
persists all campaign artifacts.

Approval requests follow:

```text
Approval Request
-> Authentication
-> Authorization
-> Approval Service
-> Transaction
-> Campaign and Workflow Update
-> Immutable Approval Record
```

Multi-row transactions use one lock order:

```text
Campaign
-> Workflow
-> Approval or related child rows
```

## Local Setup

Create a local `.env` from `.env.example`, then start PostgreSQL:

```bash
docker compose up -d postgres
docker compose ps
docker compose logs postgres
```

Install dependencies and run migrations:

```bash
python -m pip install -r requirements.txt
alembic upgrade head
```

Run the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints:

- `GET /`
- `GET /health`
- `GET /ready`
- `GET /docs`
- `POST /campaigns`
- `POST /workflows/campaigns/{campaign_id}`
- `POST /workflows/{workflow_id}/run`
- `POST /approvals`
- `GET /agent-runs`
- `GET /agent-runs/{agent_run_id}`
- `GET /agent-runs/{agent_run_id}/tool-calls`
- `GET /workflows/{workflow_id}/agent-runs`
- `GET /campaigns/{campaign_id}/agent-runs`

## Workflow Behavior

`POST /workflows/{workflow_id}/run` executes a deterministic synchronous workflow
with short database checkpoints. Database rows are not locked while an LLM call is
running. The app reserves an LLM call, commits that counter, calls the configured
Agent loop, then locks the rows again before persisting the result. Each Agent LLM
turn also reserves the workflow-level LLM count, so Agent budgets cannot bypass the
M3 workflow limit.

## Agent Runtime

Each specialist run is bounded by `AGENT_MAX_ITERATIONS`, `AGENT_MAX_LLM_CALLS`,
`AGENT_MAX_TOOL_CALLS`, and `AGENT_TIMEOUT_SECONDS`. Execution stops on validated
final output, a provider or validation failure, timeout, or any exhausted limit.
There is no recursive or unbounded loop.

M4 tools expose only fresh, read-only views of prior workflow summaries, revisions,
and quality feedback. A tool reads through `AgentReadQueryService`, then a repository,
inside a short lock-free PostgreSQL read transaction. Inputs are schema validated and
scoped to the run's campaign/workflow; outputs are sanitized, treated as untrusted,
and truncated to `AGENT_MAX_TOOL_RESULT_CHARACTERS`. There are no shell, filesystem,
network, or write-capable Agent tools.

Each specialist receives a frozen, typed context containing only what it needs. The
analyst receives campaign brief data, the generator receives validated analysis and
relevant revision feedback, and the reviewer receives the analysis plus generated
content. Contexts contain no ORM objects, database sessions, credentials, or provider
payloads.

Every specialist execution creates an `agent_runs` audit row with prompt version and
counters. Its lifecycle is `CREATED -> RUNNING -> COMPLETED`, with `FAILED` and
`LIMIT_EXCEEDED` as terminal alternatives. Every attempted tool execution creates an
`agent_tool_calls` row with sanitized arguments, bounded result summary, status,
duration, and safe error fields. Tool calls move from `REQUESTED` to `RUNNING` and
then to `COMPLETED` or `FAILED`; rejected requests terminate as `REJECTED`. Internal
tool timeouts, outer Agent timeouts, and explicit task cancellation are finalized as
safe terminal audit records, so no interrupted call remains `RUNNING`. Prompts,
hidden reasoning, provider payloads, and raw database errors are not persisted.

`MockLLMClient` supports `scripted_turns` containing `AgentTurn` values for fully
deterministic tool-call/final-output tests. Default tests never contact a real LLM.

Content generation is retried only for bounded review failures:

```text
GENERATING -> REVIEWING -> GENERATING
```

Retries stop when `MAX_CONTENT_RETRIES` is exhausted. A passing review reaches
`PENDING_APPROVAL`. A review with `MANUAL_REVIEW_REQUIRED`, or exhausted retries,
stays in `MANUAL_REVIEW_REQUIRED`; it is not silently promoted to final approval.

If workflow execution fails before a terminal/manual/approval state, the failure is
persisted as `FAILED` with a stable error code and a sanitized error message.

Approval decisions are append-only. The database enforces one approval record per
workflow. A revision request closes the old workflow at `REVISION_REQUIRED`,
increments the campaign version, and leaves the campaign in `REVISION_REQUIRED`.
Create a new workflow for that campaign to continue revision generation; the new
workflow starts at `REVISION_REQUIRED`, stores `parent_workflow_id`, increments
`revision_number`, and can run back to `PENDING_APPROVAL`.

The database also enforces one active workflow per campaign with a PostgreSQL
partial unique index over active statuses where `completed_at IS NULL`.

Workflow creation is allowed only for campaigns in `RECEIVED` or
`REVISION_REQUIRED`. Approved, rejected, failed, pending approval, and manual
review campaigns cannot be reopened implicitly.

Approval and Agent-run audit APIs require authentication. Agent-run audit reads are
authorized only for `REVIEWER`, `MANAGER`, `ADMIN`, and `SYSTEM`; other authenticated
roles receive `403`. In development and tests, requests may pass `x-actor-id` and
`x-actor-role`; production should use Bearer JWTs with `sub` and `role` claims.

The audit API returns identifiers, lifecycle status, counters, timestamps, sanitized
bounded tool arguments/results, and stable safe error fields. It never returns raw
prompts, hidden reasoning, credentials, provider payloads, or raw database details.

## Database

The app uses async SQLAlchemy with `postgresql+asyncpg`.
Production schema changes are handled through Alembic, not `create_all()`.

Migration commands:

```bash
alembic upgrade head
alembic current
alembic history
alembic downgrade -1
alembic check
```

Reset local database volume:

```bash
docker compose down -v
```

## Quality Checks

```bash
python -m ruff check app tests
python -m ruff format --check app tests
python -m mypy app
python -m bandit -r app
python -m pytest -v
python -m pytest --cov=app --cov-report=term-missing
```

PostgreSQL integration and E2E tests are guarded to avoid mutating a developer
database accidentally. Run them only against a migrated test database:

```bash
set RUN_POSTGRES_TESTS=1
python -m pytest tests/integration -v
```

Run the complete deterministic M4 suite and coverage report with:

```bash
set RUN_POSTGRES_TESTS=1
set LLM_PROVIDER=mock
python -m pytest -v
python -m pytest --cov=app --cov-report=term-missing
```

CI sets `RUN_POSTGRES_TESTS=1`, starts PostgreSQL, applies Alembic migrations,
runs an Alembic drift check, and executes the full quality suite. The PostgreSQL
suite covers repository persistence, database constraints, workflow/service
lifecycle behavior, approval conflicts, concurrency, API flows, and E2E approval,
revision, retry, and failure scenarios.

## Security

Production rejects unsafe `change-me` secrets. The mock LLM provider requires no API
key and is the default for tests. Real OpenAI usage requires `LLM_PROVIDER=openai`,
`LLM_API_KEY`, and `LLM_MODEL`.

## Current Limitations and M5

M4 keeps execution synchronous and has no long-term, episodic, or semantic memory.
M4 tools are read-only. Agents do not approve campaigns. Agents do not publish
campaigns. Agents do not directly change workflow state. It does not include queues,
controlled write actions, a policy engine, action approval, vector retrieval,
autonomous publication, supervisor delegation, external integrations, or advanced
evaluation/tracing. Those safety, action, memory, and observability capabilities
remain deferred to M5 or later. Manual review resolution from
`MANUAL_REVIEW_REQUIRED` also remains a future explicit product flow.
