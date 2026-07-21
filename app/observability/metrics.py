from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ("method", "route", "status")
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ("method", "route")
)
HTTP_ERRORS = Counter("http_errors_total", "HTTP errors", ("method", "route", "status"))

JOBS_ENQUEUED = Counter("jobs_enqueued_total", "Jobs enqueued", ("job_type",))
JOBS_STARTED = Counter("jobs_started_total", "Jobs started", ("job_type",))
JOBS_SUCCEEDED = Counter("jobs_succeeded_total", "Jobs succeeded", ("job_type",))
JOBS_FAILED = Counter("jobs_failed_total", "Jobs failed", ("job_type", "status"))
JOBS_DEAD_LETTER = Counter(
    "jobs_dead_letter_total", "Jobs moved to dead letter", ("job_type",)
)
JOB_DURATION = Histogram(
    "job_duration_seconds", "Job handler duration", ("job_type", "status")
)
JOBS_PENDING = Gauge("jobs_pending", "Pending jobs")
JOBS_RUNNING = Gauge("jobs_running", "Running jobs")
OLDEST_PENDING_JOB = Gauge(
    "oldest_pending_job_seconds", "Age of the oldest pending job"
)

WORKFLOW_RUNS = Counter("workflow_runs_total", "Workflow runs", ("status",))
WORKFLOW_DURATION = Histogram(
    "workflow_duration_seconds", "Workflow duration", ("status",)
)
WORKFLOW_FAILURES = Counter("workflow_failures_total", "Workflow failures")
WORKFLOW_RETRIES = Counter("workflow_retries_total", "Workflow retries")
WORKFLOW_MANUAL_REVIEWS = Counter(
    "workflow_manual_reviews_total", "Workflow manual reviews"
)

AGENT_RUNS = Counter("agent_runs_total", "Agent runs", ("agent_name", "status"))
AGENT_RUN_DURATION = Histogram(
    "agent_run_duration_seconds", "Agent run duration", ("agent_name", "status")
)
AGENT_FAILURES = Counter("agent_failures_total", "Agent failures", ("agent_name",))
AGENT_LIMIT_EXCEEDED = Counter(
    "agent_limit_exceeded_total", "Agent limit exceeded", ("limit_type",)
)
AGENT_LLM_CALLS = Counter("agent_llm_calls_total", "Agent LLM calls", ("agent_name",))
AGENT_TOOL_CALLS = Counter(
    "agent_tool_calls_total", "Agent tool calls", ("agent_name", "tool_name")
)

POLICY_DECISIONS = Counter(
    "policy_decisions_total", "Policy decisions", ("decision", "action_name")
)
ACTION_REQUESTS = Counter(
    "action_requests_total", "Action requests", ("action_name", "status")
)
ACTION_EXECUTIONS = Counter(
    "action_executions_total", "Action executions", ("action_name", "status")
)
ACTION_EXECUTION_FAILURES = Counter(
    "action_execution_failures_total", "Action execution failures", ("action_name",)
)
ACTION_POLICY_DENIALS = Counter(
    "action_policy_reevaluation_denials_total",
    "Fresh policy reevaluation denials",
    ("action_name",),
)
ACTION_APPROVAL_DURATION = Histogram(
    "action_approval_duration_seconds", "Action approval duration", ("action_name",)
)

OUTBOX_PENDING = Gauge("outbox_pending", "Pending or failed outbox events")
OUTBOX_FAILED = Counter(
    "outbox_failed_total", "Outbox consumer failures", ("event_type",)
)
OUTBOX_DURATION = Histogram(
    "outbox_processing_duration_seconds",
    "Outbox processing duration",
    ("event_type", "status"),
)

LLM_REQUESTS = Counter("llm_requests_total", "LLM requests", ("provider", "model"))
LLM_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration",
    ("provider", "model", "status"),
)
LLM_FAILURES = Counter("llm_failures_total", "LLM failures", ("provider", "model"))
LLM_INPUT_TOKENS = Counter(
    "llm_input_tokens_total", "LLM input tokens", ("provider", "model")
)
LLM_OUTPUT_TOKENS = Counter(
    "llm_output_tokens_total", "LLM output tokens", ("provider", "model")
)
LLM_ESTIMATED_COST = Counter(
    "llm_estimated_cost_total", "Estimated LLM cost", ("provider", "model")
)
