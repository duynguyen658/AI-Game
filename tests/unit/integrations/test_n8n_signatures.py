from datetime import UTC, datetime

import pytest

from app.core.exceptions import WebhookAuthenticationError
from app.integrations.n8n.signatures import sign_webhook, verify_webhook


def test_n8n_hmac_timestamp_and_constant_time_verification() -> None:
    now = datetime(2026, 7, 21, tzinfo=UTC)
    timestamp = str(int(now.timestamp()))
    body = b'{"campaign":{"campaign_id":"M7"}}'
    signature = sign_webhook("secret", timestamp, body)
    assert (
        len(
            verify_webhook(
                "secret", timestamp, body, signature, tolerance_seconds=300, now=now
            )
        )
        == 64
    )
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(
            "secret", timestamp, body + b"x", signature, tolerance_seconds=300, now=now
        )
    with pytest.raises(WebhookAuthenticationError):
        verify_webhook(
            "secret",
            str(int(now.timestamp()) - 301),
            body,
            signature,
            tolerance_seconds=300,
            now=now,
        )
