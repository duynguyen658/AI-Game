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

## Security

Production rejects unsafe `change-me` secrets. The mock LLM provider requires no API
key and is the default for tests. Real OpenAI usage requires `LLM_PROVIDER=openai`,
`LLM_API_KEY`, and `LLM_MODEL`.

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
