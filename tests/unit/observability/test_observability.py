from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import get_settings

from app.observability.logging import redact_log_event
from app.observability import metrics as metric_definitions
from app.observability.middleware import valid_or_new_correlation_id
from app.observability.middleware import OperationalMiddleware


def test_correlation_id_is_propagated_or_replaced() -> None:
    expected = "6a6e1b0d-596f-49e8-8381-72fb1e036adb"
    assert valid_or_new_correlation_id(expected) == expected
    assert valid_or_new_correlation_id("not-a-uuid") != "not-a-uuid"
    UUID(valid_or_new_correlation_id(None))


def test_structured_log_redaction_is_recursive() -> None:
    event = redact_log_event(
        None,
        "info",
        {
            "event": "test",
            "authorization": "Bearer abc.def",
            "nested": {"api_key": "sk-test", "safe": "ok"},
            "message": "password=super-secret",
        },
    )
    assert event["authorization"] == "[REDACTED]"
    assert event["nested"]["api_key"] == "[REDACTED]"
    assert event["nested"]["safe"] == "ok"
    assert "super-secret" not in event["message"]


def body_limit_client() -> TestClient:
    app = FastAPI()
    settings = get_settings().model_copy(update={"max_request_body_bytes": 1024})
    app.add_middleware(OperationalMiddleware, settings=settings)

    @app.post("/body")
    async def read_body(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return TestClient(app)


def test_actual_body_limit_accepts_small_request() -> None:
    response = body_limit_client().post("/body", content=b"a" * 100)
    assert response.status_code == 200
    assert response.json() == {"size": 100}


def test_content_length_fast_check_preserves_correlation_id() -> None:
    correlation_id = "6a6e1b0d-596f-49e8-8381-72fb1e036adb"
    response = body_limit_client().post(
        "/body",
        content=b"small",
        headers={
            "content-length": "2048",
            "x-correlation-id": correlation_id,
        },
    )
    assert response.status_code == 413
    assert response.json()["error_code"] == "REQUEST_BODY_TOO_LARGE"
    assert response.headers["x-correlation-id"] == correlation_id


def test_actual_bytes_reject_missing_content_length_chunked_body() -> None:
    def chunks():
        yield b"a" * 600
        yield b"b" * 600

    response = body_limit_client().post("/body", content=chunks())
    assert response.status_code == 413
    assert response.json()["error_code"] == "REQUEST_BODY_TOO_LARGE"


def test_actual_bytes_override_incorrect_small_content_length() -> None:
    response = body_limit_client().post(
        "/body", content=b"a" * 1200, headers={"content-length": "1"}
    )
    assert response.status_code == 413


def test_malformed_content_length_is_rejected_safely() -> None:
    response = body_limit_client().post(
        "/body", content=b"small", headers={"content-length": "invalid"}
    )
    assert response.status_code == 413


def test_negative_content_length_is_rejected_safely() -> None:
    response = body_limit_client().post(
        "/body", content=b"small", headers={"content-length": "-1"}
    )
    assert response.status_code == 413


def test_metric_labels_are_low_cardinality() -> None:
    forbidden = {
        "campaign_id",
        "workflow_id",
        "job_id",
        "user_id",
        "error_message",
        "url",
    }
    for value in vars(metric_definitions).values():
        label_names = set(getattr(value, "_labelnames", ()))
        assert label_names.isdisjoint(forbidden)
