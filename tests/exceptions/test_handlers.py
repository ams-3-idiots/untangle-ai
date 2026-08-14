"""도메인 예외와 요청 검증 실패가 ProblemDetail 응답으로 변환되는지 검증한다."""

import json

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.exceptions.ai import AINotConfiguredError, AI_UNAVAILABLE_MESSAGE
from app.exceptions.handlers import domain_error_handler, error_responses
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.main import app
from app.schemas.error import ProblemDetail


def _request() -> Request:
    """핸들러가 쓰지 않는 요청 자리를 채울 최소 객체를 만든다."""
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def test_domain_error_becomes_problem_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    # 준비: provider 설정을 비워 503 도메인 예외를 일으킨다.
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = client.post("/api/v1/ai/brain-dump", json={"text": "발표 준비해야 해."})

    assert response.status_code == 503
    assert response.json() == {
        "type": "about:blank",
        "title": "AI service unavailable",
        "status": 503,
        "detail": AI_UNAVAILABLE_MESSAGE,
    }


def test_domain_error_uses_problem_media_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = client.post("/api/v1/ai/brain-dump", json={"text": "발표 준비해야 해."})

    assert response.headers["content-type"].startswith("application/problem+json")


def test_validation_error_becomes_problem_detail(client: TestClient):
    response = client.post("/api/v1/ai/brain-dump", json={"text": "   "})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Validation failed"
    assert body["status"] == 422
    assert body["detail"].startswith("text: ")


def test_validation_error_uses_problem_media_type(client: TestClient):
    response = client.post("/api/v1/ai/brain-dump", json={"text": "   "})

    assert response.headers["content-type"].startswith("application/problem+json")


def test_validation_detail_includes_nested_field_path(client: TestClient):
    response = client.post(
        "/api/v1/ai/brain-dump",
        json={
            "text": "요즘 너무 바빠.",
            "clarifications": [
                {
                    "key": "action_detail",
                    "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
                    "answer": "발표 준비",
                    "skipped": True,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "clarifications.0" in response.json()["detail"]


def test_validation_detail_joins_multiple_errors(client: TestClient):
    response = client.post(
        "/api/v1/ai/brain-dump", json={"text": "   ", "clarifications": "문자열"}
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "text" in detail
    assert "clarifications" in detail
    assert "; " in detail


def test_unparseable_json_detail_has_no_field_path(client: TestClient):
    response = client.post(
        "/api/v1/ai/brain-dump",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "JSON decode error"


def test_session_not_found_becomes_404_problem_detail():
    response = domain_error_handler(
        _request(), SessionNotFoundError("ai session not found: cace6837")
    )

    assert response.status_code == 404
    assert json.loads(response.body) == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "ai session not found: cace6837",
    }


def test_protection_limit_becomes_429_problem_detail():
    response = domain_error_handler(
        _request(), ProtectionLimitError("too many requests")
    )

    assert response.status_code == 429
    assert json.loads(response.body) == {
        "type": "about:blank",
        "title": "Too many requests",
        "status": 429,
        "detail": "too many requests",
    }


def test_error_responses_declares_problem_media_type():
    responses = error_responses(AINotConfiguredError)

    assert responses[503]["description"] == AINotConfiguredError.description
    content = responses[503]["content"]
    assert list(content) == ["application/problem+json"]
    assert content["application/problem+json"]["schema"] == (
        ProblemDetail.model_json_schema()
    )


def test_openapi_declares_problem_detail_for_422():
    schema = app.openapi()

    responses = schema["paths"]["/api/v1/ai/brain-dump"]["post"]["responses"]
    content = responses["422"]["content"]
    assert list(content) == ["application/problem+json"]
    assert content["application/problem+json"]["schema"]["title"] == "ProblemDetail"
