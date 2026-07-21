from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from app.core.exceptions import WebhookAuthenticationError


def sign_webhook(secret: str, timestamp: str, raw_body: bytes) -> str:
    material = timestamp.encode("ascii") + b"." + raw_body
    return hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()


def verify_webhook(
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
    *,
    tolerance_seconds: int,
    now: datetime | None = None,
) -> str:
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise WebhookAuthenticationError("Webhook timestamp is invalid") from exc
    current = now or datetime.now(UTC)
    if abs(int(current.timestamp()) - timestamp_value) > tolerance_seconds:
        raise WebhookAuthenticationError(
            "Webhook timestamp is outside the allowed window"
        )
    expected = sign_webhook(secret, timestamp, raw_body)
    normalized = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, normalized):
        raise WebhookAuthenticationError("Webhook signature is invalid")
    return hashlib.sha256(normalized.encode()).hexdigest()
