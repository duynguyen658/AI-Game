# Milestone 7 Architecture

M7 keeps deterministic workflow state, policy decisions, approvals, jobs, outbox delivery, and PostgreSQL audit as authorities. Managed prompts are resolved before a provider call and their immutable version provenance is copied to each AgentRun.

Applied workflows are declared by `AppliedWorkflowRegistry`. Upload endpoints persist bounded inputs and enqueue typed jobs. Workers load a snapshot in a short transaction, close it before provider or file processing, then persist the typed result and outbox event in a new transaction. CSV arithmetic and document extraction are deterministic; LLMs only explain or summarize supplied results. Media can only advance to human review.

n8n inbound requests are authenticated over the raw body with timestamped HMAC-SHA256. A PostgreSQL receipt provides replay and idempotency protection. The stable M8 surfaces are the workflow catalog, prompt library and experiments, provider catalog/comparison, impact analytics, feedback, media assets, task/job status, data reports, document results, and review actions.

Prompt experiments and provider comparisons execute managed prompt versions against an immutable dataset snapshot through registered adapters. Case output, normalized usage, latency, failures, aggregate metrics, and configuration provenance are persisted by background jobs. Client-supplied result metrics are rejected, and experiment winners are never activated automatically.

Applied task, media, experiment, and comparison state is reconciled when a job is cancelled or exhausts retries. Retrying clears terminal errors while retaining prior case and media-attempt audit rows. Business-impact records reference real completed tasks and derive provider, model, prompt, duration, and cost from execution evidence.

Media attempts carry job-attempt and worker ownership. The worker validates the live lease inside the short success transaction that updates attempt, asset, task, and outbox together. Failure and cancellation use a separate guarded terminalization transaction; terminal-job reconciliation is the bounded recovery path. Attempt numbers are allocated while locking the asset row.

M7 persistence maps `IntegrityError` by exact PostgreSQL constraint name. Known idempotency constraints can return an existing resource or a stable conflict. Foreign-key, check, null, and unknown violations become safe persistence errors after rollback. Business-impact analytics keep technical success separate from nullable human acceptance.
