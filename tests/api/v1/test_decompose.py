"""할 일 쪼개기 API의 경로·상태 코드·본문과 헤더 호환성을 검증한다."""

from fastapi.testclient import TestClient

from app.exceptions.ai import AI_UNAVAILABLE_MESSAGE, AIProviderError
from app.main import app
from app.schemas.decompose import DecomposeItemModelOutput, DecomposeModelOutput
from app.services import session_service

START_PATH = "/api/v1/ai-sessions/decompose"
START_BODY = {"target": {"title": "운동 시작하기", "notes": None}, "instruction": None}

TASK_DRAFT_FIELDS = {
    "title",
    "memo",
    "importance",
    "estimatedMinutes",
    "dueDate",
    "dueTime",
    "reminderMinutesBefore",
    "sourceExcerpt",
}


def _continue_path(session_id: str) -> str:
    """이어가기 경로를 만든다."""
    return f"/api/v1/ai-sessions/{session_id}/decompose"


def _documented_example(request_name: str) -> dict:
    """생성된 OpenAPI 문서가 `Try it out`에 채워 넣는 요청 예시를 꺼낸다."""
    schemas = app.openapi()["components"]["schemas"]
    return schemas[f"Decompose{request_name}Request"]["examples"][0]


def _question() -> DecomposeModelOutput:
    """질문 턴 모델 출력을 만든다."""
    return DecomposeModelOutput(
        needs_clarification=True,
        assistant_text="운동을 시작하려는 주된 목적이 뭔가요?",
        options=["체중 감량", "체력 증진"],
        items=[],
        first_step=None,
    )


def _decomposition() -> DecomposeModelOutput:
    """분해 턴 모델 출력을 만든다."""
    return DecomposeModelOutput(
        needs_clarification=False,
        assistant_text="가볍게 시작할 수 있게 나눴어요.",
        options=[],
        items=[
            DecomposeItemModelOutput(
                title="운동화 꺼내기", importance=1, estimated_minutes=2
            )
        ],
        first_step=None,
    )


def test_start_returns_201(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(START_PATH, json=START_BODY)

    assert response.status_code == 201


def test_start_returns_the_documented_response_fields(client: TestClient, fake_llm):
    fake_llm(_question())

    body = client.post(START_PATH, json=START_BODY).json()

    assert set(body) == {
        "sessionId",
        "proposalId",
        "items",
        "options",
        "firstStep",
        "assistantText",
    }


def test_question_turn_leaves_items_null(client: TestClient, fake_llm):
    fake_llm(_question())

    body = client.post(START_PATH, json=START_BODY).json()

    assert body["items"] is None
    assert body["options"] == ["체중 감량", "체력 증진"]


def test_decomposition_turn_leaves_options_null(client: TestClient, fake_llm):
    fake_llm(_decomposition())

    body = client.post(START_PATH, json=START_BODY).json()

    assert body["options"] is None
    assert len(body["items"]) == 1


def test_first_step_is_always_null(client: TestClient, fake_llm):
    fake_llm(_decomposition())

    body = client.post(START_PATH, json=START_BODY).json()

    assert body["firstStep"] is None


def test_proposal_id_equals_session_id(client: TestClient, fake_llm):
    fake_llm(_question())

    body = client.post(START_PATH, json=START_BODY).json()

    assert body["proposalId"] == body["sessionId"]


def test_items_keep_every_task_draft_field(client: TestClient, fake_llm):
    fake_llm(_decomposition())

    body = client.post(START_PATH, json=START_BODY).json()

    assert set(body["items"][0]) == TASK_DRAFT_FIELDS


def test_item_source_excerpt_is_the_target_title(client: TestClient, fake_llm):
    fake_llm(_decomposition())

    body = client.post(START_PATH, json=START_BODY).json()

    assert body["items"][0]["sourceExcerpt"] == "운동 시작하기"


def test_start_example_body_is_accepted(client: TestClient, fake_llm):
    # 준비: Swagger의 `Try it out`에 채워지는 예시를 수정 없이 보낸다.
    fake_llm(_question())

    response = client.post(START_PATH, json=_documented_example("Start"))

    assert response.status_code == 201


def test_continue_example_body_is_accepted(client: TestClient, fake_llm):
    fake_llm(_question(), _decomposition())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]

    response = client.post(
        _continue_path(session_id), json=_documented_example("Message")
    )

    assert response.status_code == 200


def test_continue_returns_200(client: TestClient, fake_llm):
    fake_llm(_question(), _decomposition())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]

    response = client.post(
        _continue_path(session_id), json={"message": "체력 증진이 목적이야"}
    )

    assert response.status_code == 200


def test_continue_keeps_the_same_session_id(client: TestClient, fake_llm):
    fake_llm(_question(), _decomposition())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]

    body = client.post(
        _continue_path(session_id), json={"message": "체력 증진이 목적이야"}
    ).json()

    assert body["sessionId"] == session_id


def test_continue_rejects_unknown_session(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(
        _continue_path("cace6837-1f4e-4a5f-9a6f-9f2c2f8f3a11"),
        json={"message": "체력 증진이 목적이야"},
    )

    assert response.status_code == 404
    assert response.json()["title"] == "Not found"


def test_continue_rejects_session_id_that_is_not_a_uuid(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(
        _continue_path("uuid가-아닌-값"), json={"message": "체력 증진이 목적이야"}
    )

    assert response.status_code == 404


def test_continue_rejects_session_without_decompose_start(client: TestClient, fake_llm):
    fake_llm(_question())
    session = session_service.create_session()

    response = client.post(
        _continue_path(session.session_id), json={"message": "체력 증진이 목적이야"}
    )

    assert response.status_code == 404


def test_start_rejects_blank_target_title(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(START_PATH, json={"target": {"title": "   "}})

    assert response.status_code == 422
    assert response.json()["title"] == "Validation failed"


def test_start_rejects_target_title_over_the_length_limit(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(START_PATH, json={"target": {"title": "가" * 501}})

    assert response.status_code == 422


def test_start_rejects_instruction_over_the_length_limit(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(
        START_PATH,
        json={"target": {"title": "운동 시작하기"}, "instruction": "가" * 2001},
    )

    assert response.status_code == 422


def test_start_rejects_missing_target(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(START_PATH, json={"instruction": None})

    assert response.status_code == 422


def test_continue_rejects_blank_message(client: TestClient, fake_llm):
    fake_llm(_question())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]

    response = client.post(_continue_path(session_id), json={"message": "   "})

    assert response.status_code == 422


def test_validation_error_uses_the_problem_detail_body(client: TestClient, fake_llm):
    fake_llm(_question())

    response = client.post(START_PATH, json={"target": {"title": "   "}})

    assert set(response.json()) == {"type", "title", "status", "detail"}
    assert response.headers["content-type"].startswith("application/problem+json")


def test_provider_failure_becomes_503(client: TestClient, fake_llm):
    fake_llm(AIProviderError(AI_UNAVAILABLE_MESSAGE))

    response = client.post(START_PATH, json=START_BODY)

    assert response.status_code == 503
    assert response.json()["title"] == "AI service unavailable"


def test_decomposition_without_items_becomes_503(client: TestClient, fake_llm):
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=False,
            assistant_text="나눴어요.",
            options=[],
            items=[],
            first_step=None,
        )
    )

    response = client.post(START_PATH, json=START_BODY)

    assert response.status_code == 503
    assert response.json()["detail"] == AI_UNAVAILABLE_MESSAGE


def test_idempotency_key_replays_the_start_response(client: TestClient, fake_llm):
    calls = fake_llm(_question())
    headers = {"Idempotency-Key": "retry-key-1"}

    first = client.post(START_PATH, json=START_BODY, headers=headers)
    second = client.post(START_PATH, json=START_BODY, headers=headers)

    assert second.json() == first.json()
    assert len(calls) == 1


def test_idempotency_key_replays_the_continue_response(client: TestClient, fake_llm):
    calls = fake_llm(_question(), _decomposition())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]
    headers = {"Idempotency-Key": "retry-key-2"}
    body = {"message": "체력 증진이 목적이야"}

    first = client.post(_continue_path(session_id), json=body, headers=headers)
    second = client.post(_continue_path(session_id), json=body, headers=headers)

    assert second.json() == first.json()
    assert len(calls) == 2


def test_replayed_continue_does_not_record_the_turn_twice(client: TestClient, fake_llm):
    fake_llm(_question(), _decomposition())
    session_id = client.post(START_PATH, json=START_BODY).json()["sessionId"]
    headers = {"Idempotency-Key": "retry-key-3"}
    body = {"message": "체력 증진이 목적이야"}
    client.post(_continue_path(session_id), json=body, headers=headers)

    client.post(_continue_path(session_id), json=body, headers=headers)

    turns = session_service.get_session(session_id).turns
    assert [turn.role for turn in turns] == ["assistant", "user", "assistant"]


def test_requests_without_idempotency_key_start_new_sessions(
    client: TestClient, fake_llm
):
    fake_llm(_question())

    first = client.post(START_PATH, json=START_BODY)
    second = client.post(START_PATH, json=START_BODY)

    assert first.json()["sessionId"] != second.json()["sessionId"]


def test_blank_idempotency_key_is_ignored(client: TestClient, fake_llm):
    fake_llm(_question())
    headers = {"Idempotency-Key": " "}

    first = client.post(START_PATH, json=START_BODY, headers=headers)
    second = client.post(START_PATH, json=START_BODY, headers=headers)

    assert first.json()["sessionId"] != second.json()["sessionId"]


def test_authorization_header_does_not_change_the_result(client: TestClient, fake_llm):
    fake_llm(_question())
    headers = {"Idempotency-Key": "auth-key-1", "Authorization": "Bearer any-token"}

    with_header = client.post(START_PATH, json=START_BODY, headers=headers)
    without_header = client.post(
        START_PATH, json=START_BODY, headers={"Idempotency-Key": "auth-key-1"}
    )

    assert with_header.status_code == 201
    assert without_header.json() == with_header.json()


def test_error_response_carries_the_request_id(client: TestClient, fake_llm):
    fake_llm(AIProviderError(AI_UNAVAILABLE_MESSAGE))

    response = client.post(
        START_PATH, json=START_BODY, headers={"X-Request-Id": "decompose-trace-1"}
    )

    assert response.headers["X-Request-Id"] == "decompose-trace-1"


def test_error_detail_excludes_user_input(client: TestClient, fake_llm):
    fake_llm(AIProviderError(AI_UNAVAILABLE_MESSAGE))

    response = client.post(
        START_PATH,
        json={"target": {"title": "010-1234-5678로 치과 예약하기"}},
    )

    assert "010-1234-5678" not in response.text
