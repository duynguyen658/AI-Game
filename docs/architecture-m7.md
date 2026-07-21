# Milestone 7 Architecture

M7 keeps deterministic workflow state, policy decisions, approvals, jobs, outbox delivery, and PostgreSQL audit as authorities. Managed prompts are resolved before a provider call and their immutable version provenance is copied to each AgentRun.

Applied workflows are declared by `AppliedWorkflowRegistry`. Upload endpoints persist bounded inputs and enqueue typed jobs. Workers load a snapshot in a short transaction, close it before provider or file processing, then persist the typed result and outbox event in a new transaction. CSV arithmetic and document extraction are deterministic; LLMs only explain or summarize supplied results. Media can only advance to human review.

n8n inbound requests are authenticated over the raw body with timestamped HMAC-SHA256. A PostgreSQL receipt provides replay and idempotency protection. The stable M8 surfaces are the workflow catalog, prompt library and experiments, provider catalog/comparison, impact analytics, feedback, media assets, task/job status, data reports, document results, and review actions.
