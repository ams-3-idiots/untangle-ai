"""Spring 호환 할 일 쪼개기의 요청·응답 형식과 모델 출력 형식을 정의한다."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.base import CamelModel
from app.schemas.task_draft import TaskDraft

MAX_ITEMS = 5
"""분해 턴이 돌려주는 전체 목록의 개수 상한."""

MIN_OPTIONS = 2
MAX_OPTIONS = 4
"""질문 턴이 성립하는 선택지 개수 범위."""

TargetTitleStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
TargetNotesStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=4000)
]
InstructionStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
]
MessageStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class DecomposeTarget(CamelModel):
    """쪼갤 할 일 한 건의 스냅샷."""

    title: TargetTitleStr = Field(description="쪼갤 할 일의 제목")
    notes: TargetNotesStr | None = Field(
        default=None, description="대상에 대한 보충 메모"
    )


class DecomposeStartRequest(CamelModel):
    """쪼개기 시작 요청: 쪼갤 대상과 분해 방식 지시."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "target": {"title": "운동 시작하기", "notes": None},
                    "instruction": None,
                }
            ]
        }
    )

    target: DecomposeTarget = Field(description="쪼갤 할 일")
    instruction: InstructionStr | None = Field(
        default=None, description="분해 방식 지시. 있으면 질문 없이 바로 분해한다"
    )


class DecomposeMessageRequest(CamelModel):
    """쪼개기 이어가기 요청: 이번 턴의 사용자 발화 하나."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"message": "체력 증진이 목적이야"}]}
    )

    message: MessageStr = Field(
        description="이번 턴의 사용자 발화. 선택지 칩 텍스트 또는 자유 입력"
    )


class DecomposeResponse(CamelModel):
    """시작·이어가기 공통 응답. `items`의 null 여부로 질문 턴과 분해 턴을 구분한다."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sessionId": "cace6837-1f4e-4a5f-9a6f-9f2c2f8f3a11",
                    "proposalId": "cace6837-1f4e-4a5f-9a6f-9f2c2f8f3a11",
                    "items": None,
                    "options": ["체중 감량", "체력 증진", "스트레스 해소"],
                    "firstStep": None,
                    "assistantText": "운동을 시작하려는 주된 목적이 뭔가요?",
                },
                {
                    "sessionId": "cace6837-1f4e-4a5f-9a6f-9f2c2f8f3a11",
                    "proposalId": "cace6837-1f4e-4a5f-9a6f-9f2c2f8f3a11",
                    "items": [
                        {
                            "title": "운동화 꺼내 현관에 두기",
                            "memo": None,
                            "importance": 1,
                            "estimatedMinutes": 2,
                            "dueDate": None,
                            "dueTime": None,
                            "reminderMinutesBefore": None,
                            "sourceExcerpt": "운동 시작하기",
                        }
                    ],
                    "options": None,
                    "firstStep": None,
                    "assistantText": "체력 증진에 맞춰 가볍게 시작할 수 있게 나눴어요.",
                },
            ]
        }
    )

    session_id: str = Field(description="이 쪼개기 대화의 세션. 이어가기 경로에 쓴다")
    proposal_id: str = Field(description="응답 식별자. `sessionId`와 항상 같은 값")
    items: list[TaskDraft] | None = Field(
        min_length=1,
        max_length=MAX_ITEMS,
        description=(
            "대상을 대체하는 전체 목록. 배열 순서가 실행 순서이며 질문 턴에서는 null"
        ),
    )
    options: list[str] | None = Field(
        min_length=MIN_OPTIONS,
        max_length=MAX_OPTIONS,
        description="질문 턴의 답변 선택지. 분해 턴에서는 null",
    )
    first_step: TaskDraft | None = Field(
        default=None,
        description="언제나 null. '지금 할 첫 단계'는 `items[0]`으로 온다",
    )
    assistant_text: str = Field(
        description="질문 턴이면 질문 한 문장, 분해 턴이면 한두 문장 설명"
    )


class DecomposeItemModelOutput(BaseModel):
    """모델이 반환한 정리 전의 쪼개기 단계 한 건."""

    model_config = ConfigDict(extra="forbid")

    title: str
    importance: int | None
    estimated_minutes: int | None


class DecomposeModelOutput(BaseModel):
    """모델이 반환한 질문 턴 또는 분해 턴."""

    model_config = ConfigDict(extra="forbid")

    needs_clarification: bool
    assistant_text: str
    options: list[str]
    items: list[DecomposeItemModelOutput]
    first_step: DecomposeItemModelOutput | None
