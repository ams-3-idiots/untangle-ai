"""덤프 `tasks[]`와 쪼개기 `items[]`가 공유하는 할 일 제안 DTO와 정규화."""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator

from app.schemas.base import CamelModel

TaskTitleStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DueDateStr = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
DueTimeStr = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]

_ALLOWED_IMPORTANCE = frozenset({1, 2, 3})
_ALLOWED_REMINDER_MINUTES = frozenset({10, 30, 60, 180, 1440})


class TaskDraft(CamelModel):
    """할 일 제안 한 건. 8개 필드는 값이 없어도 키를 생략하지 않고 null로 직렬화한다."""

    title: TaskTitleStr = Field(description="할 일 제목. 항상 비공백")
    memo: str | None = Field(
        default=None, description="제목에 담지 못한 보충 메모. null이면 단서 없음"
    )
    importance: Literal[1, 2, 3] | None = Field(
        default=None, description="중요도. 1=높음, 2=중간, 3=낮음, null이면 단서 없음"
    )
    estimated_minutes: int | None = Field(
        default=None, gt=0, description="예상 소요 시간(분). null이면 단서 없음"
    )
    due_date: DueDateStr | None = Field(
        default=None, description="마감 날짜(`yyyy-MM-dd`). null이면 단서 없음"
    )
    due_time: DueTimeStr | None = Field(
        default=None, description="마감 시각(`HH:mm`, 24시간제). null이면 단서 없음"
    )
    reminder_minutes_before: Literal[10, 30, 60, 180, 1440] | None = Field(
        default=None, description="마감 전 알림 시점(분). null이면 알림 없음"
    )
    source_excerpt: str | None = Field(
        default=None, description="이 할 일이 추출된 근거 원문 일부. null이면 단서 없음"
    )

    @field_validator("due_date")
    @classmethod
    def _check_real_date(cls, value: str | None) -> str | None:
        """패턴만으로 거를 수 없는 13월·32일 같은 날짜를 막는다."""
        if value is not None:
            date.fromisoformat(value)
        return value


def normalize_task_drafts(items: Iterable[Mapping[str, Any]]) -> list[TaskDraft]:
    """모델 출력을 공통 정규화 규칙에 맞춰 `TaskDraft` 목록으로 만든다.

    입력 키는 python 필드 이름(snake_case) 기준이다. 제목이 공백뿐인 항목은
    버리고, 제목의 `strip + 소문자`가 같으면 첫 항목만 남긴다(순서 유지).
    """
    seen_titles: set[str] = set()
    drafts: list[TaskDraft] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        dedupe_key = title.lower()
        if dedupe_key in seen_titles:
            continue
        seen_titles.add(dedupe_key)
        drafts.append(
            TaskDraft(
                title=title,
                memo=item.get("memo") or None,
                importance=_allowed_or_none(
                    item.get("importance"), _ALLOWED_IMPORTANCE
                ),
                estimated_minutes=_positive_or_none(item.get("estimated_minutes")),
                due_date=item.get("due_date") or None,
                due_time=item.get("due_time") or None,
                reminder_minutes_before=_allowed_or_none(
                    item.get("reminder_minutes_before"), _ALLOWED_REMINDER_MINUTES
                ),
                source_excerpt=item.get("source_excerpt"),
            )
        )
    return drafts


def _allowed_or_none(value: Any, allowed: frozenset[int]) -> Any:
    """허용 목록 밖의 값을 단서 없음(null)으로 바꾼다."""
    # bool은 int의 서브클래스라 True가 1과 같다고 판정돼 통과하는 것을 막는다.
    if isinstance(value, bool):
        return None
    return value if value in allowed else None


def _positive_or_none(value: Any) -> Any:
    """0 이하이거나 수가 아닌 예상 소요 시간을 단서 없음(null)으로 바꾼다."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if value > 0 else None
