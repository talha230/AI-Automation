"""API tests using a stubbed assistant — no network or API key required."""

import pytest
from fastapi.testclient import TestClient

from app.assistant import AssistantError
from app.main import app
from app.schemas import RequirementsDocument


def _sample_document() -> RequirementsDocument:
    return RequirementsDocument(
        project_name="ToolShare",
        summary="Borrow and lend tools with neighbours.",
        functional_requirements=[],
        non_functional_requirements=[],
        user_stories=[],
        assumptions=[],
        out_of_scope=[],
        risks=[],
        clarifying_questions=[],
    )


class _StubAssistant:
    """Stands in for the real Claude-backed assistant."""

    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def generate(self, req):
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def client():
    # Entering the context manager runs the lifespan, which builds the real
    # assistant; we then swap in a stub so no network call is made.
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "api_key_configured" in body


def test_requirements_success(client):
    app.state.assistant = _StubAssistant(result=_sample_document())
    resp = client.post("/requirements", json={"idea": "A tool-sharing app."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["project_name"] == "ToolShare"
    assert "request_id" in body
    assert resp.headers.get("x-request-id")


def test_requirements_validation_error(client):
    resp = client.post("/requirements", json={"idea": "no"})
    assert resp.status_code == 422  # idea below min_length


def test_requirements_upstream_failure_is_502(client):
    app.state.assistant = _StubAssistant(error=AssistantError("boom"))
    resp = client.post("/requirements", json={"idea": "A tool-sharing app."})
    assert resp.status_code == 502
    assert resp.json()["error"] == "boom"


def test_missing_credentials_surface_as_assistant_error():
    """A non-APIError SDK failure (e.g. no credentials -> TypeError) must be
    converted to AssistantError, not leak as an unhandled 500."""
    from app.assistant import RequirementsAssistant
    from app.config import Settings
    from app.schemas import RequirementsRequest

    assistant = RequirementsAssistant(Settings(anthropic_api_key=None))
    # Simulate the SDK's "could not resolve authentication method" TypeError.
    assistant._client.messages.parse = lambda **_: (_ for _ in ()).throw(
        TypeError("Could not resolve authentication method.")
    )
    with pytest.raises(AssistantError):
        assistant.generate(RequirementsRequest(idea="A tool-sharing app."))
