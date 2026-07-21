# Information Architecture

## Workspace

- `/dashboard`: operational and impact overview.
- `/tasks`: authorized Applied AI workflow catalog.
- `/campaigns`: campaign list, creation, and detail.
- `/data-analysis`: CSV task creation and report detail.
- `/documents`: document task creation and result detail.
- `/media`: image generation, media review, and storyboards.

## AI operations

- `/prompts`: prompt templates, versions, and lifecycle commands.
- `/prompt-experiments`: experiment creation, execution, and results.
- `/provider-comparisons`: provider catalog, comparison execution, and results.
- `/approvals`: campaign, controlled action, prompt, and media review queues where
  supported by backend read contracts.

## Business

- `/analytics/business-impact`: authoritative impact and acceptance metrics.
- Feedback is embedded in eligible task and workflow details.

## Operations

- `/operations/jobs`: job queue and operator commands.
- `/operations/alerts`: alert lifecycle.
- `/operations/health`: public health signals and operator summary.
- `/integrations/n8n`: safe integration documentation and workflow downloads.

Authentication routes are `/login`, `/logout`, `/session-expired`, and `/forbidden`.
Deep links remain stable and use readable context before displaying identifiers.
