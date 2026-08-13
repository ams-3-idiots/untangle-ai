"""TaskDraft의 검증·직렬화와 공통 정규화 규칙을 검증한다."""

import pytest
from pydantic import ValidationError

from app.schemas.task_draft import TaskDraft, normalize_task_drafts


def test_serializes_all_eight_fields_with_null():
    draft = TaskDraft(title="발표 자료 준비하기")

    assert draft.model_dump(by_alias=True) == {
        "title": "발표 자료 준비하기",
        "memo": None,
        "importance": None,
        "estimatedMinutes": None,
        "dueDate": None,
        "dueTime": None,
        "reminderMinutesBefore": None,
        "sourceExcerpt": None,
    }


def test_accepts_camel_case_wire_input():
    draft = TaskDraft.model_validate(
        {"title": "발표 준비", "estimatedMinutes": 30, "dueDate": "2026-08-20"}
    )

    assert draft.estimated_minutes == 30
    assert draft.due_date == "2026-08-20"


def test_rejects_blank_title():
    with pytest.raises(ValidationError):
        TaskDraft(title="   ")


def test_rejects_impossible_due_date():
    with pytest.raises(ValidationError):
        TaskDraft(title="발표 준비", due_date="2026-13-40")


def test_rejects_due_time_out_of_range():
    with pytest.raises(ValidationError):
        TaskDraft(title="발표 준비", due_time="24:10")


def test_normalize_drops_blank_title_items():
    drafts = normalize_task_drafts([{"title": "   "}, {"title": "발표 준비"}])

    assert [draft.title for draft in drafts] == ["발표 준비"]


def test_normalize_deduplicates_titles_keeping_first():
    drafts = normalize_task_drafts(
        [
            {"title": "발표 준비", "memo": "첫 항목"},
            {"title": " 발표 준비 ", "memo": "중복"},
            {"title": "Send Mail"},
            {"title": "send mail"},
        ]
    )

    assert [draft.title for draft in drafts] == ["발표 준비", "Send Mail"]
    assert drafts[0].memo == "첫 항목"


def test_normalize_nullifies_out_of_range_importance():
    drafts = normalize_task_drafts([{"title": "발표 준비", "importance": 4}])

    assert drafts[0].importance is None


def test_normalize_keeps_allowed_importance():
    drafts = normalize_task_drafts([{"title": "발표 준비", "importance": 2}])

    assert drafts[0].importance == 2


def test_normalize_nullifies_non_positive_estimated_minutes():
    drafts = normalize_task_drafts([{"title": "발표 준비", "estimated_minutes": 0}])

    assert drafts[0].estimated_minutes is None


def test_normalize_nullifies_boolean_values():
    drafts = normalize_task_drafts(
        [
            {
                "title": "발표 준비",
                "importance": True,
                "estimated_minutes": True,
                "reminder_minutes_before": True,
            }
        ]
    )

    assert drafts[0].importance is None
    assert drafts[0].estimated_minutes is None
    assert drafts[0].reminder_minutes_before is None


def test_normalize_keeps_integral_float_estimated_minutes():
    drafts = normalize_task_drafts([{"title": "발표 준비", "estimated_minutes": 90.0}])

    assert drafts[0].estimated_minutes == 90


def test_normalize_truncates_fractional_estimated_minutes():
    drafts = normalize_task_drafts([{"title": "발표 준비", "estimated_minutes": 30.5}])

    assert drafts[0].estimated_minutes == 30


def test_normalize_nullifies_estimated_minutes_truncated_to_zero():
    drafts = normalize_task_drafts([{"title": "발표 준비", "estimated_minutes": 0.5}])

    assert drafts[0].estimated_minutes is None


def test_normalize_nullifies_disallowed_reminder_minutes():
    drafts = normalize_task_drafts(
        [{"title": "발표 준비", "reminder_minutes_before": 15}]
    )

    assert drafts[0].reminder_minutes_before is None


def test_normalize_nullifies_empty_strings():
    drafts = normalize_task_drafts(
        [{"title": "발표 준비", "memo": "", "due_date": "", "due_time": ""}]
    )

    assert drafts[0].memo is None
    assert drafts[0].due_date is None
    assert drafts[0].due_time is None


def test_normalize_keeps_valid_values():
    drafts = normalize_task_drafts(
        [
            {
                "title": " 발표 자료 준비하기 ",
                "memo": "슬라이드 10장",
                "importance": 1,
                "estimated_minutes": 90,
                "due_date": "2026-08-20",
                "due_time": "18:30",
                "reminder_minutes_before": 60,
                "source_excerpt": "다음 주 발표가 있어",
            }
        ]
    )

    assert drafts[0].model_dump(by_alias=True) == {
        "title": "발표 자료 준비하기",
        "memo": "슬라이드 10장",
        "importance": 1,
        "estimatedMinutes": 90,
        "dueDate": "2026-08-20",
        "dueTime": "18:30",
        "reminderMinutesBefore": 60,
        "sourceExcerpt": "다음 주 발표가 있어",
    }
