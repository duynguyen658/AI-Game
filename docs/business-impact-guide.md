# Business Impact Guide

Create a manual baseline per task type and department, then record one impact row for each completed task run. The backend calculates minutes saved and automation rate with `Decimal`; it also aggregates first-pass acceptance, revision rate, error rate, estimated cost, satisfaction, and willingness to reuse.

Feedback is owned by actor and task. A repeat submission must include the current version, preventing lost updates. Comments are bounded and sanitized, and feedback never changes workflow state. Operator analytics support task, department, provider, model, prompt-version, and date filters for M8 tables and charts.
