from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def test_root_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["application"] == "Cyber Legends AI Workflow"
    assert payload["docs"] == "/docs"


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "healthy"

    timestamp = datetime.fromisoformat(payload["timestamp"])
    assert timestamp.tzinfo is not None
