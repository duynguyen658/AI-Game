# Business Impact Guide

Create a manual baseline per task type and department, then record one impact row for each completed task run. The backend calculates minutes saved and automation rate with `Decimal`; it also aggregates first-pass acceptance, revision rate, error rate, estimated cost, satisfaction, and willingness to reuse.

Feedback is owned by actor and task. A repeat submission must include the current version, preventing lost updates. Comments are bounded and sanitized, and feedback never changes workflow state. Operator analytics support task, department, provider, model, prompt-version, and date filters for M8 tables and charts.

Impact requests may contain only human evidence: department or an authorized manual-baseline override, steps, acceptance/editing, rework, and reported errors. The service requires a real eligible task and derives task type, job, prompt version, provider/model, AI duration, and estimated cost from persisted execution provenance. Random task IDs, non-terminal tasks, and unrelated actors are rejected. Feedback applies the same task ownership and eligibility checks and copies prompt/provider/model from the task.

Technical completion and human acceptance are separate. `task_completed_successfully` is server-derived, while `output_accepted` is nullable until an authorized user submits a decision or a media review records approval/rejection. A completed task is not automatically considered accepted. `accepted_without_editing=true` requires explicit acceptance, zero editing minutes, and zero rework.

`human_acceptance_rate` and first-pass acceptance use only rows with known acceptance as their denominator. `technical_success_rate` uses completed execution evidence. Unknown database constraints are persistence failures, not duplicate conflicts; only the named impact and actor/task feedback uniqueness constraints map to stable conflicts.
