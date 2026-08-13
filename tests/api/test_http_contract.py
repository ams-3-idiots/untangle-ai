"""모든 응답이 공유하는 `X-Request-Id`·`Authorization` 계약을 검증한다."""

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ai import BrainDumpCompletedOutput


def _completed_output() -> BrainDumpCompletedOutput:
    """완료 상태의 브레인덤프 모델 출력을 만든다."""
    return BrainDumpCompletedOutput.model_validate(
        {
            "status": "completed",
            "result": {"candidates": [{"title": "발표 자료 준비하기", "memo": ""}]},
        }
    )


def test_response_includes_generated_request_id(client: TestClient):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert uuid.UUID(response.headers["X-Request-Id"])


def test_valid_request_id_is_echoed(client: TestClient):
    response = client.get("/api/v1/health", headers={"X-Request-Id": "trace_01.A-b"})

    assert response.headers["X-Request-Id"] == "trace_01.A-b"


def test_request_id_with_disallowed_characters_is_replaced(client: TestClient):
    response = client.get("/api/v1/health", headers={"X-Request-Id": "trace id!"})

    assert response.headers["X-Request-Id"] != "trace id!"
    assert uuid.UUID(response.headers["X-Request-Id"])


def test_request_id_over_64_chars_is_replaced(client: TestClient):
    long_id = "a" * 65

    response = client.get("/api/v1/health", headers={"X-Request-Id": long_id})

    assert response.headers["X-Request-Id"] != long_id
    assert uuid.UUID(response.headers["X-Request-Id"])


def test_error_response_includes_request_id(client: TestClient):
    response = client.post(
        "/api/v1/ai/brain-dump",
        json={"text": "   "},
        headers={"X-Request-Id": "err-trace-1"},
    )

    assert response.status_code == 422
    assert response.headers["X-Request-Id"] == "err-trace-1"


def test_unhandled_error_response_includes_request_id(fake_llm):
    # 준비: DomainError가 아닌 예외로 핸들러 없는 500 경로를 만든다.
    fake_llm(RuntimeError("검증용 미처리 예외"))

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/ai/brain-dump",
            json={"text": "발표 준비해야 해."},
            headers={"X-Request-Id": "err-trace-500"},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "err-trace-500"


def test_request_id_is_used_in_server_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    # 레벨을 강제로 올리지 않아야 앱의 로깅 설정이 실제로 동작하는지 확인된다.
    client.get("/api/v1/health", headers={"X-Request-Id": "log-trace-1"})

    assert any("log-trace-1" in record.getMessage() for record in caplog.records)


def test_app_logger_emits_info_records():
    assert logging.getLogger("app.request").isEnabledFor(logging.INFO)


def test_request_without_authorization_succeeds(client: TestClient, fake_llm):
    fake_llm(_completed_output())

    response = client.post("/api/v1/ai/brain-dump", json={"text": "발표 준비해야 해."})

    assert response.status_code == 200


def test_authorization_header_does_not_change_result(client: TestClient, fake_llm):
    fake_llm(_completed_output())
    body = {"text": "발표 준비해야 해."}

    without_header = client.post("/api/v1/ai/brain-dump", json=body)
    with_header = client.post(
        "/api/v1/ai/brain-dump",
        json=body,
        headers={"Authorization": "Bearer any-token"},
    )

    assert without_header.status_code == 200
    assert with_header.status_code == 200
    assert with_header.json() == without_header.json()
