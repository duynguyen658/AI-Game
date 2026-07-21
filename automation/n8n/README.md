# n8n Workflow Pack

Import the four JSON files into n8n and keep each workflow inactive until its credentials and environment variables are configured.

Required environment variables:

- `AI_GAME_API_URL`: backend origin, for example `https://api.example.internal`
- `AI_GAME_API_TOKEN`: scoped manager/operator token for authenticated API reads
- `AI_GAME_WEBHOOK_SIGNATURE`: HMAC signature generated from `timestamp + "." + raw_body`
- `APPROVAL_SLACK_CHANNEL` and `CRITICAL_ALERT_SLACK_CHANNEL`
- `CAMPAIGN_REPORT_SHEET_ID`

Configure Slack and Google Sheets credentials in n8n's credential store. Never place tokens or the webhook secret in workflow JSON. Inbound backend calls require `X-N8N-Timestamp`, `X-N8N-Signature`, and a unique `X-Idempotency-Key`. HTTP nodes use bounded retries and route terminal failures to n8n error outputs; connect those outputs to your environment's incident workflow before activation.

The sample signature expression is a placeholder because n8n installations differ in crypto-node availability. Generate the HMAC in a credential-backed Code node or gateway and assign it to `AI_GAME_WEBHOOK_SIGNATURE`; do not expose `N8N_WEBHOOK_SECRET` to form submissions.
