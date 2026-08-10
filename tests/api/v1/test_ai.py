"""AI 브레인덤프·할 일 쪼개기 API의 요청과 응답을 검증한다."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.exceptions.ai import AIProviderError
from app.schemas.ai import (
    BrainDumpClarificationOutput,
    BrainDumpCompletedOutput,
    TaskBreakdownClarificationOutput,
    TaskBreakdownCompletedOutput,
)


def _brain_dump_completed(candidates: list[dict]) -> BrainDumpCompletedOutput:
    """완료 상태의 브레인덤프 모델 출력을 만든다."""
    return BrainDumpCompletedOutput.model_validate(
        {"status": "completed", "result": {"candidates": candidates}}
    )


def _breakdown_completed(
    first_step: dict | None, steps: list[dict]
) -> TaskBreakdownCompletedOutput:
    """완료 상태의 쪼개기 모델 출력을 만든다."""
    return TaskBreakdownCompletedOutput.model_validate(
        {"status": "completed", "result": {"first_step": first_step, "steps": steps}}
    )


def test_brain_dump_returns_completed_candidates(client: TestClient, fake_llm):
    # 준비
    fake_llm(_brain_dump_completed([{"title": "발표 자료 준비하기", "memo": ""}]))

    # 실행
    response = client.post(
        "/api/v1/ai/brain-dump",
        json={"text": "요즘 일이 너무 복잡해서 뭘 해야 할지 모르겠어."},
    )

    # 확인
    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "result": {"candidates": [{"title": "발표 자료 준비하기", "memo": ""}]},
    }


def test_brain_dump_returns_clarification_question(client: TestClient, fake_llm):
    fake_llm(
        BrainDumpClarificationOutput.model_validate(
            {
                "status": "needs_clarification",
                "question": {
                    "key": "action_detail",
                    "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
                    "options": [],
                },
            }
        )
    )

    response = client.post("/api/v1/ai/brain-dump", json={"text": "머리가 복잡해."})

    assert response.status_code == 200
    assert response.json() == {
        "status": "needs_clarification",
        "question": {
            "key": "action_detail",
            "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
            "options": [],
        },
    }


def test_brain_dump_returns_completed_after_answer(client: TestClient, fake_llm):
    # 준비: 스펙 6.2의 재요청처럼 답변 하나가 실린 이력을 함께 보낸다.
    fake_llm(
        _brain_dump_completed([{"title": "다음 주 발표 자료 준비하기", "memo": ""}])
    )

    response = client.post(
        "/api/v1/ai/brain-dump",
        json={
            "text": "요즘 일이 너무 복잡해서 뭘 해야 할지 모르겠어.",
            "clarifications": [
                {
                    "key": "action_detail",
                    "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
                    "answer": "다음 주 발표 자료를 준비해야 해.",
                    "skipped": False,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "result": {"candidates": [{"title": "다음 주 발표 자료 준비하기", "memo": ""}]},
    }


def test_brain_dump_rejects_blank_text(client: TestClient):
    response = client.post("/api/v1/ai/brain-dump", json={"text": "   "})

    assert response.status_code == 422
    assert any("text" in error["loc"] for error in response.json()["detail"])


def test_brain_dump_rejects_answer_with_skipped_true(client: TestClient):
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
    assert any("clarifications" in error["loc"] for error in response.json()["detail"])


def test_brain_dump_rejects_disallowed_key(client: TestClient):
    response = client.post(
        "/api/v1/ai/brain-dump",
        json={
            "text": "요즘 너무 바빠.",
            "clarifications": [
                {
                    "key": "progress",
                    "text": "어디까지 되어 있나요?",
                    "answer": "아직 시작 전",
                    "skipped": False,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert any("key" in error["loc"] for error in response.json()["detail"])


def test_brain_dump_rejects_duplicate_key(client: TestClient, fake_llm):
    # 준비: 요청이 잘못됐으므로 LLM은 호출되면 안 된다.
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))
    answer = {
        "key": "action_detail",
        "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
        "answer": "발표 준비",
        "skipped": False,
    }

    response = client.post(
        "/api/v1/ai/brain-dump",
        json={"text": "요즘 너무 바빠.", "clarifications": [answer, answer]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_clarification_state"


def test_brain_dump_returns_503_when_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = client.post("/api/v1/ai/brain-dump", json={"text": "발표 준비해야 해."})

    assert response.status_code == 503
    assert response.json()["code"] == "ai_not_configured"


def test_brain_dump_returns_502_on_provider_error(client: TestClient, fake_llm):
    fake_llm(
        AIProviderError("AI 응답을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
    )

    response = client.post("/api/v1/ai/brain-dump", json={"text": "발표 준비해야 해."})

    assert response.status_code == 502
    assert response.json()["code"] == "ai_provider_error"


def test_task_breakdown_returns_completed_steps(client: TestClient, fake_llm):
    fake_llm(
        _breakdown_completed(
            {"title": "새 포트폴리오 문서 파일 열기", "memo": ""},
            [{"title": "첫 프로젝트의 문제와 해결 방법 적기", "memo": "초안만"}],
        )
    )

    response = client.post(
        "/api/v1/ai/task-breakdown", json={"goal": "이직용 포트폴리오 만들기"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "result": {
            "first_step": {"title": "새 포트폴리오 문서 파일 열기", "memo": ""},
            "steps": [
                {"title": "첫 프로젝트의 문제와 해결 방법 적기", "memo": "초안만"}
            ],
        },
    }


def test_task_breakdown_returns_clarification_question(client: TestClient, fake_llm):
    fake_llm(
        TaskBreakdownClarificationOutput.model_validate(
            {
                "status": "needs_clarification",
                "question": {
                    "key": "progress",
                    "text": "지금 어디까지 되어 있나요?",
                    "options": ["아직 시작 전이에요", "초안이 있어요"],
                },
            }
        )
    )

    response = client.post(
        "/api/v1/ai/task-breakdown", json={"goal": "이직용 포트폴리오 만들기"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "needs_clarification",
        "question": {
            "key": "progress",
            "text": "지금 어디까지 되어 있나요?",
            "options": ["아직 시작 전이에요", "초안이 있어요"],
        },
    }


def test_task_breakdown_returns_empty_result(client: TestClient, fake_llm):
    fake_llm(_breakdown_completed(None, []))

    response = client.post(
        "/api/v1/ai/task-breakdown", json={"goal": "이직용 포트폴리오 만들기"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "result": {"first_step": None, "steps": []},
    }


def test_task_breakdown_rejects_long_goal(client: TestClient):
    response = client.post("/api/v1/ai/task-breakdown", json={"goal": "가" * 101})

    assert response.status_code == 422
    assert any("goal" in error["loc"] for error in response.json()["detail"])


def test_task_breakdown_returns_503_when_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = client.post(
        "/api/v1/ai/task-breakdown", json={"goal": "이직용 포트폴리오 만들기"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "ai_not_configured"


def test_task_breakdown_rejects_clarifications_over_limit(client: TestClient, fake_llm):
    # 준비: 요청이 잘못됐으므로 LLM은 호출되면 안 된다.
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))
    clarifications = [
        {"key": key, "text": "질문입니다.", "answer": "답입니다.", "skipped": False}
        for key in ["progress", "done", "capacity", "blocker"]
    ]

    response = client.post(
        "/api/v1/ai/task-breakdown",
        json={"goal": "이직용 포트폴리오 만들기", "clarifications": clarifications},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_clarification_state"


def test_task_breakdown_rejects_steps_without_first_step(client: TestClient, fake_llm):
    fake_llm(_breakdown_completed(None, [{"title": "아무 단계", "memo": ""}]))

    response = client.post(
        "/api/v1/ai/task-breakdown", json={"goal": "이직용 포트폴리오 만들기"}
    )

    assert response.status_code == 502
    assert response.json()["code"] == "invalid_ai_response"
