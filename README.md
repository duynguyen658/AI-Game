# Cyber Legends AI Workflow Backend

Production-oriented FastAPI backend for a deterministic AI-assisted campaign workflow.
This milestone intentionally excludes Agentic AI. The application controls workflow
state, retries, approval decisions, persistence, authorization, and audit history.

## Architecture

```text
FastAPI Router
-> Application Service
-> Deterministic Workflow
-> LLM Client when required
-> Repository
-> PostgreSQL
```

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

## Workflow Behavior

`POST /workflows/{workflow_id}/run` executes a deterministic synchronous workflow
with short database checkpoints. Database rows are not locked while an LLM call is
running. The app reserves an LLM call, commits that counter, calls the configured
LLM client, then locks the rows again before persisting the result.

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

Approval APIs require authentication. In development and tests, approval requests
may pass `x-actor-id` and `x-actor-role`; production should use Bearer JWTs with
`sub` and `role` claims.

## Database

The app uses async SQLAlchemy with `postgresql+asyncpg`.
Production schema changes are handled through Alembic, not `create_all()`.

Migration commands:

```bash
alembic upgrade head
alembic current
alembic history
alembic downgrade -1
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

CI sets `RUN_POSTGRES_TESTS=1`, starts PostgreSQL, applies Alembic migrations,
and runs the full quality suite.

## Security

Production rejects unsafe `change-me` secrets. The mock LLM provider requires no API
key and is the default for tests. Real OpenAI usage requires `LLM_PROVIDER=openai`,
`LLM_API_KEY`, and `LLM_MODEL`.

## Current Limitations

M3 keeps workflow execution synchronous. It does not include queues, background
workers, publication integrations, or Agentic AI orchestration. Manual review
resolution from `MANUAL_REVIEW_REQUIRED` remains a future explicit product flow.

## Deferred Agentic AI Work

Deferred to a later milestone:

- Agent runtime
- LLM agents
- Supervisor agent
- Tool registry and tool execution
- Agent policy engine
- Agent memory
- Vector search and retrieval
- Autonomous planning
- MCP integration
- Multi-agent collaboration
