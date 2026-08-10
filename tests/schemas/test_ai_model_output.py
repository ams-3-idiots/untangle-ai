"""모델 출력 union DTO가 스펙 5.5의 상호 배타 규칙을 강제하는지 검증한다."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.ai import BrainDumpModelOutput, TaskBreakdownModelOutput


def test_brain_dump_output_rejects_question_with_result():
    # 준비: needs_clarification인데 result까지 함께 실린 잘못된 출력이다.
    payload = {
        "status": "needs_clarification",
        "question": {
            "key": "action_detail",
            "text": "무엇을 해야 하나요?",
            "options": [],
        },
        "result": {"candidates": []},
    }

    with pytest.raises(ValidationError):
        TypeAdapter(BrainDumpModelOutput).validate_python(payload)


def test_brain_dump_output_rejects_status_only():
    with pytest.raises(ValidationError):
        TypeAdapter(BrainDumpModelOutput).validate_python({"status": "completed"})


def test_task_breakdown_output_rejects_question_with_result():
    payload = {
        "status": "needs_clarification",
        "question": {"key": "progress", "text": "어디까지 되었나요?", "options": []},
        "result": {"first_step": None, "steps": []},
    }

    with pytest.raises(ValidationError):
        TypeAdapter(TaskBreakdownModelOutput).validate_python(payload)


def test_task_breakdown_output_rejects_status_only():
    with pytest.raises(ValidationError):
        TypeAdapter(TaskBreakdownModelOutput).validate_python(
            {"status": "needs_clarification"}
        )
