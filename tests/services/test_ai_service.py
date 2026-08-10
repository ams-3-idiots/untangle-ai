"""브레인덤프·할 일 쪼개기 서비스의 업무 규칙을 검증한다."""

import pytest

from app.exceptions.ai import (
    InvalidAIResponseError,
    InvalidClarificationStateError,
)
from app.schemas.ai import (
    BrainDumpClarificationOutput,
    BrainDumpCompletedOutput,
    BrainDumpRequest,
    TaskBreakdownClarificationOutput,
    TaskBreakdownCompletedOutput,
    TaskBreakdownRequest,
)
from app.services import ai_service


def _brain_dump_completed(candidates: list[dict]) -> BrainDumpCompletedOutput:
    """완료 상태의 브레인덤프 모델 출력을 만든다."""
    return BrainDumpCompletedOutput.model_validate(
        {"status": "completed", "result": {"candidates": candidates}}
    )


def _brain_dump_question() -> BrainDumpClarificationOutput:
    """action_detail을 묻는 브레인덤프 모델 출력을 만든다."""
    return BrainDumpClarificationOutput.model_validate(
        {
            "status": "needs_clarification",
            "question": {
                "key": "action_detail",
                "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
                "options": [],
            },
        }
    )


def _breakdown_completed(
    first_step: dict | None, steps: list[dict]
) -> TaskBreakdownCompletedOutput:
    """완료 상태의 쪼개기 모델 출력을 만든다."""
    return TaskBreakdownCompletedOutput.model_validate(
        {"status": "completed", "result": {"first_step": first_step, "steps": steps}}
    )


def _breakdown_question(
    key: str, options: list[str] | None = None
) -> TaskBreakdownClarificationOutput:
    """주어진 key를 묻는 쪼개기 모델 출력을 만든다."""
    return TaskBreakdownClarificationOutput.model_validate(
        {
            "status": "needs_clarification",
            "question": {"key": key, "text": "질문입니다.", "options": options or []},
        }
    )


def _answered(key: str, answer: str = "답입니다.") -> dict:
    """답변이 담긴 구체화 이력 항목을 만든다."""
    return {"key": key, "text": "질문입니다.", "answer": answer, "skipped": False}


def _skipped(key: str) -> dict:
    """건너뛴 구체화 이력 항목을 만든다."""
    return {"key": key, "text": "질문입니다.", "answer": None, "skipped": True}


def test_brain_dump_trims_and_deduplicates_titles(fake_llm):
    # 준비: 앞뒤 공백과 대소문자만 다른 제목이 섞여 있다.
    fake_llm(
        _brain_dump_completed(
            [
                {"title": "  Send Email ", "memo": " 이번 주 안에 "},
                {"title": "send email", "memo": "중복이라 버려진다"},
                {"title": "치과 예약하기", "memo": ""},
            ]
        )
    )

    # 실행
    response = ai_service.run_brain_dump(BrainDumpRequest(text="할 일이 많아."))

    # 확인: 첫 후보만 남고 순서가 유지되며 공백이 정리된다.
    assert response.status == "completed"
    titles = [candidate.title for candidate in response.result.candidates]
    assert titles == ["Send Email", "치과 예약하기"]
    assert response.result.candidates[0].memo == "이번 주 안에"


def test_brain_dump_limits_candidates_to_five(fake_llm):
    fake_llm(
        _brain_dump_completed(
            [{"title": f"할 일 {index}", "memo": ""} for index in range(7)]
        )
    )

    response = ai_service.run_brain_dump(BrainDumpRequest(text="할 일이 많아."))

    titles = [candidate.title for candidate in response.result.candidates]
    assert titles == [f"할 일 {index}" for index in range(5)]


def test_brain_dump_accepts_empty_candidates(fake_llm):
    fake_llm(_brain_dump_completed([]))

    response = ai_service.run_brain_dump(BrainDumpRequest(text="그냥 피곤하다."))

    assert response.status == "completed"
    assert response.result.candidates == []


def test_brain_dump_rejects_blank_candidate_title(fake_llm):
    fake_llm(_brain_dump_completed([{"title": "   ", "memo": ""}]))

    with pytest.raises(InvalidAIResponseError):
        ai_service.run_brain_dump(BrainDumpRequest(text="할 일이 많아."))


def test_brain_dump_rejects_second_question(fake_llm):
    # 준비: 이미 한 번 답했으므로 질문 한도에 도달한 상태다.
    fake_llm(_brain_dump_question())
    request = BrainDumpRequest(
        text="요즘 너무 바빠.", clarifications=[_answered("action_detail")]
    )

    with pytest.raises(InvalidAIResponseError):
        ai_service.run_brain_dump(request)


def test_task_breakdown_rejects_duplicate_key_before_llm_call(fake_llm):
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))
    request = TaskBreakdownRequest(
        goal="포트폴리오 만들기",
        clarifications=[_answered("progress"), _answered("progress", "다른 답")],
    )

    with pytest.raises(InvalidClarificationStateError):
        ai_service.run_task_breakdown(request)


def test_task_breakdown_rejects_question_for_skipped_key(fake_llm):
    # 준비: progress를 건너뛰었는데 모델이 같은 key를 다시 묻는다.
    fake_llm(_breakdown_question("progress"))
    request = TaskBreakdownRequest(
        goal="포트폴리오 만들기", clarifications=[_skipped("progress")]
    )

    with pytest.raises(InvalidAIResponseError):
        ai_service.run_task_breakdown(request)


def test_task_breakdown_rejects_question_at_limit(fake_llm):
    # 준비: 질문 3회를 모두 썼는데 모델이 네 번째 질문을 반환한다.
    fake_llm(_breakdown_question("blocker"))
    request = TaskBreakdownRequest(
        goal="포트폴리오 만들기",
        clarifications=[
            _answered("progress"),
            _answered("done"),
            _skipped("capacity"),
        ],
    )

    with pytest.raises(InvalidAIResponseError):
        ai_service.run_task_breakdown(request)


def test_task_breakdown_completes_at_question_limit(fake_llm):
    # 준비: 건너뛰기를 포함해 질문 3회를 모두 쓴, 정확히 한도인 이력이다.
    fake_llm(
        _breakdown_completed(
            {"title": "첫걸음", "memo": ""}, [{"title": "다음 단계", "memo": ""}]
        )
    )
    request = TaskBreakdownRequest(
        goal="포트폴리오 만들기",
        clarifications=[
            _answered("progress"),
            _answered("done"),
            _skipped("capacity"),
        ],
    )

    response = ai_service.run_task_breakdown(request)

    assert response.status == "completed"
    assert response.result.first_step.title == "첫걸음"
    assert [step.title for step in response.result.steps] == ["다음 단계"]


def test_task_breakdown_rejects_single_option_question(fake_llm):
    fake_llm(_breakdown_question("progress", options=["아직 시작 전이에요"]))

    with pytest.raises(InvalidAIResponseError):
        ai_service.run_task_breakdown(TaskBreakdownRequest(goal="포트폴리오 만들기"))


def test_task_breakdown_keeps_first_step_on_duplicate(fake_llm):
    fake_llm(
        _breakdown_completed(
            {"title": "자료 조사하기", "memo": ""},
            [
                {"title": " 자료 조사하기 ", "memo": "중복이라 버려진다"},
                {"title": "개요 잡기", "memo": ""},
            ],
        )
    )

    response = ai_service.run_task_breakdown(
        TaskBreakdownRequest(goal="포트폴리오 만들기")
    )

    assert response.result.first_step.title == "자료 조사하기"
    assert [step.title for step in response.result.steps] == ["개요 잡기"]


def test_task_breakdown_limits_total_steps_to_five(fake_llm):
    fake_llm(
        _breakdown_completed(
            {"title": "첫걸음", "memo": ""},
            [{"title": f"단계 {index}", "memo": ""} for index in range(6)],
        )
    )

    response = ai_service.run_task_breakdown(
        TaskBreakdownRequest(goal="포트폴리오 만들기")
    )

    # first_step을 포함해 5개까지만 남는다.
    assert [step.title for step in response.result.steps] == [
        f"단계 {index}" for index in range(4)
    ]
