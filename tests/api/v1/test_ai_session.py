"""AI 세션 생성과 브레인덤프 API의 요청과 응답을 검증한다."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.exceptions.ai import AI_UNAVAILABLE_MESSAGE, AIProviderError
from app.schemas.ai_session import DumpModelOutput
from app.services import llm_service

DUMP_TEXT = "졸업논문 중간발표가 2주 뒤인데 아직 데이터 정리도 안 했어."

_EMPTY_TASK = {
    "title": "",
    "memo": None,
    "importance": None,
    "estimated_minutes": None,
    "due_date": None,
    "due_time": None,
    "reminder_minutes_before": None,
    "source_excerpt": None,
}


def _model_output(
    tasks: list[dict], assistant_text: str = "일단 눈에 보이는 것부터 나눠봤어요."
) -> DumpModelOutput:
    """모델이 반환한 덤프 결과를 만든다 — 적지 않은 필드는 null로 채운다."""
    return DumpModelOutput.model_validate(
        {
            "tasks": [_EMPTY_TASK | task for task in tasks],
            "assistant_text": assistant_text,
        }
    )


def _dump_body(**overrides: object) -> dict:
    """기본 덤프 요청 본문에서 필요한 값만 바꿔 넣는다."""
    return {"text": DUMP_TEXT, "existingTaskTitles": []} | overrides


@pytest.fixture
def session_id(client: TestClient) -> str:
    """덤프 요청에 사용할 세션을 만들어 식별자를 돌려준다."""
    return client.post("/api/v1/ai-sessions").json()["sessionId"]


@pytest.fixture
def counting_llm(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """호출될 때마다 기록을 남기는 LLM 대역을 설치하고 그 기록을 돌려준다."""
    calls: list[str] = []

    def fake_generate_structured(
        instructions: str, input_text: str, output_type: type
    ) -> object:
        """호출 횟수에 따라 구분되는 덤프 결과를 반환한다."""
        calls.append(input_text)
        return _model_output([{"title": f"할 일 {len(calls)}"}])

    monkeypatch.setattr(llm_service, "generate_structured", fake_generate_structured)
    return calls


def test_create_session_returns_created_session_id(client: TestClient):
    # 준비: 세션 생성은 본문 없이 호출한다.

    # 실행
    response = client.post("/api/v1/ai-sessions")

    # 확인
    assert response.status_code == 201
    assert uuid.UUID(response.json()["sessionId"])


def test_create_session_issues_a_different_id_each_time(client: TestClient):
    first = client.post("/api/v1/ai-sessions").json()["sessionId"]
    second = client.post("/api/v1/ai-sessions").json()["sessionId"]

    assert first != second


def test_create_session_returns_429_over_session_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "max_sessions", 1)
    client.post("/api/v1/ai-sessions")

    response = client.post("/api/v1/ai-sessions")

    assert response.status_code == 429
    assert response.json()["title"] == "Too many requests"


def test_dump_returns_tasks_for_live_session(
    client: TestClient, fake_llm, session_id: str
):
    # 준비
    fake_llm(
        _model_output(
            [
                {
                    "title": "논문 데이터 정리하기",
                    "memo": "중간발표 전까지 완료 필요",
                    "importance": 1,
                    "estimated_minutes": 300,
                    "due_date": "2026-07-23",
                    "reminder_minutes_before": 60,
                    "source_excerpt": "아직 데이터 정리도 안 했어",
                }
            ]
        )
    )

    # 실행
    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    # 확인
    assert response.status_code == 200
    assert response.json() == {
        "proposalId": session_id,
        "tasks": [
            {
                "title": "논문 데이터 정리하기",
                "memo": "중간발표 전까지 완료 필요",
                "importance": 1,
                "estimatedMinutes": 300,
                "dueDate": "2026-07-23",
                "dueTime": None,
                "reminderMinutesBefore": 60,
                "sourceExcerpt": "아직 데이터 정리도 안 했어",
            }
        ],
        "assistantText": "일단 눈에 보이는 것부터 나눠봤어요.",
    }


def test_dump_returns_empty_tasks_with_guidance(
    client: TestClient, fake_llm, session_id: str
):
    fake_llm(
        _model_output([], assistant_text="어떤 일이 남았는지 조금만 더 적어줄래요?")
    )

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert response.status_code == 200
    assert response.json()["tasks"] == []


def test_dump_returns_guidance_when_no_task_is_found(
    client: TestClient, fake_llm, session_id: str
):
    # 준비: 후보가 없을 때는 다시 적을 내용을 안내해야 한다.
    fake_llm(
        _model_output([], assistant_text="어떤 일이 남았는지 조금만 더 적어줄래요?")
    )

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert (
        response.json()["assistantText"] == "어떤 일이 남았는지 조금만 더 적어줄래요?"
    )


def test_dump_returns_404_for_unissued_session(client: TestClient, fake_llm):
    # 준비: 세션이 없으므로 LLM은 호출되면 안 된다.
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))

    response = client.post(
        f"/api/v1/ai-sessions/{uuid.uuid4()}/dump", json=_dump_body()
    )

    assert response.status_code == 404
    assert response.json()["title"] == "Not found"


def test_dump_returns_404_for_session_id_that_is_not_a_uuid(
    client: TestClient, fake_llm
):
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))

    response = client.post("/api/v1/ai-sessions/cace6837/dump", json=_dump_body())

    assert response.status_code == 404


def test_dump_rejects_blank_text(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(text="   ")
    )

    assert response.status_code == 422
    assert "text" in response.json()["detail"]


def test_dump_rejects_text_over_max_length(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(text="가" * 8001)
    )

    assert response.status_code == 422
    assert "text" in response.json()["detail"]


def test_dump_rejects_missing_existing_task_titles(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json={"text": DUMP_TEXT}
    )

    assert response.status_code == 422
    assert "existingTaskTitles" in response.json()["detail"]


def test_dump_rejects_null_existing_task_titles(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump",
        json=_dump_body(existingTaskTitles=None),
    )

    assert response.status_code == 422
    assert "existingTaskTitles" in response.json()["detail"]


def test_dump_rejects_too_many_existing_task_titles(
    client: TestClient, session_id: str
):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump",
        json=_dump_body(existingTaskTitles=[f"할 일 {index}" for index in range(201)]),
    )

    assert response.status_code == 422
    assert "existingTaskTitles" in response.json()["detail"]


def test_dump_rejects_long_existing_task_title(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump",
        json=_dump_body(existingTaskTitles=["가" * 501]),
    )

    assert response.status_code == 422
    assert "existingTaskTitles" in response.json()["detail"]


def test_dump_rejects_long_client_now(client: TestClient, session_id: str):
    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(clientNow="0" * 41)
    )

    assert response.status_code == 422
    assert "clientNow" in response.json()["detail"]


def test_dump_accepts_client_now_that_is_not_a_timestamp(
    client: TestClient, fake_llm, session_id: str
):
    # 준비: clientNow는 길이만 제한하고 형식은 검증하지 않는다.
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))

    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump",
        json=_dump_body(clientNow="어제 밤"),
    )

    assert response.status_code == 200


def test_dump_returns_503_when_model_returns_no_result(
    client: TestClient, fake_llm, session_id: str
):
    # 준비: 후보도 안내 문구도 없는 응답은 쓸 수 없다.
    fake_llm(_model_output([], assistant_text="   "))

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert response.status_code == 503
    assert response.json()["title"] == "AI service unavailable"


def test_dump_returns_503_on_provider_error(
    client: TestClient, fake_llm, session_id: str
):
    fake_llm(AIProviderError(AI_UNAVAILABLE_MESSAGE))

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert response.status_code == 503
    assert response.json()["detail"] == AI_UNAVAILABLE_MESSAGE


def test_dump_returns_503_when_not_configured(
    client: TestClient, session_id: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert response.status_code == 503
    assert response.json()["title"] == "AI service unavailable"


def test_dump_returns_429_over_rate_limit(
    client: TestClient, fake_llm, session_id: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "rate_limit_requests", 0)
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))

    response = client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert response.status_code == 429
    assert response.json()["title"] == "Too many requests"


def test_dump_reuses_response_for_same_idempotency_key(
    client: TestClient, counting_llm: list[str], session_id: str
):
    # 준비: 네트워크 오류로 같은 키를 다시 보내는 앱의 재시도를 재현한다.
    headers = {"Idempotency-Key": "retry-1"}
    first = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )

    second = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )

    assert second.status_code == 200
    assert second.json() == first.json()


def test_dump_calls_llm_once_for_same_idempotency_key(
    client: TestClient, counting_llm: list[str], session_id: str
):
    headers = {"Idempotency-Key": "retry-1"}

    client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )
    second = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )

    assert second.status_code == 200
    assert len(counting_llm) == 1


def test_dump_reused_from_cache_does_not_consume_rate_limit(
    client: TestClient,
    counting_llm: list[str],
    session_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    # 준비: 첫 요청이 한 번뿐인 한도를 모두 쓰게 만든다.
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    headers = {"Idempotency-Key": "retry-1"}
    client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )

    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body(), headers=headers
    )

    assert response.status_code == 200


def test_dump_without_idempotency_key_calls_llm_again(
    client: TestClient, counting_llm: list[str], session_id: str
):
    client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())
    client.post(f"/api/v1/ai-sessions/{session_id}/dump", json=_dump_body())

    assert len(counting_llm) == 2


def test_dump_response_includes_request_id(
    client: TestClient, fake_llm, session_id: str
):
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))

    response = client.post(
        f"/api/v1/ai-sessions/{session_id}/dump",
        json=_dump_body(),
        headers={"X-Request-Id": "dump-trace-1"},
    )

    assert response.headers["X-Request-Id"] == "dump-trace-1"
