"""AI 브레인덤프·할 일 쪼개기의 요청·응답 형식과 모델 출력 형식을 정의한다."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

BrainDumpKey = Literal["action_detail"]
TaskBreakdownKey = Literal["progress", "done", "capacity", "blocker"]

MAX_RESULT_ITEMS = 5
"""브레인덤프 후보와 쪼개기 단계(first_step 포함)가 공유하는 개수 상한."""

TitleStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
MemoStr = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
QuestionTextStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
OptionStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
AnswerStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
BrainDumpTextStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class TodoCandidate(BaseModel):
    """브레인덤프 후보와 쪼개기 단계에 공통으로 쓰는 할 일 한 건."""

    title: TitleStr
    memo: MemoStr = ""


class ClarificationQuestion[KeyT](BaseModel):
    """정보가 부족할 때 사용자에게 되묻는 질문."""

    key: KeyT
    text: QuestionTextStr
    options: list[OptionStr] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def _check_options_count(cls, value: list[str]) -> list[str]:
        """선택지는 아예 없거나 2~4개만 허용한다."""
        if len(value) == 1 or len(value) > 4:
            raise ValueError("options는 0개 또는 2~4개여야 합니다.")
        return value


class ClarificationAnswer[KeyT](BaseModel):
    """서버가 던진 질문에 대한 답변 또는 건너뛰기 기록."""

    key: KeyT
    text: QuestionTextStr
    answer: AnswerStr | None = None
    skipped: bool

    @model_validator(mode="after")
    def _check_answer_matches_skipped(self) -> "ClarificationAnswer[KeyT]":
        """건너뛴 질문에는 answer가 없어야 하고, 답한 질문에는 있어야 한다."""
        if self.skipped and self.answer is not None:
            raise ValueError("건너뛴 질문에는 answer를 담을 수 없습니다.")
        if not self.skipped and self.answer is None:
            raise ValueError("답한 질문에는 비어 있지 않은 answer가 필요합니다.")
        return self


class BrainDumpRequest(BaseModel):
    """브레인덤프 요청: 원본 입력과 누적 구체화 이력."""

    text: BrainDumpTextStr
    clarifications: list[ClarificationAnswer[BrainDumpKey]] = Field(
        default_factory=list
    )


class TaskBreakdownRequest(BaseModel):
    """할 일 쪼개기 요청: 목표 한 줄과 누적 구체화 이력."""

    goal: TitleStr
    clarifications: list[ClarificationAnswer[TaskBreakdownKey]] = Field(
        default_factory=list
    )


class BrainDumpResult(BaseModel):
    """브레인덤프가 만든 할 일 후보 목록."""

    candidates: list[TodoCandidate] = Field(max_length=MAX_RESULT_ITEMS)


class BrainDumpClarificationResponse(BaseModel):
    """질문 하나가 더 필요한 브레인덤프 응답."""

    status: Literal["needs_clarification"] = "needs_clarification"
    question: ClarificationQuestion[BrainDumpKey]


class BrainDumpCompletedResponse(BaseModel):
    """후보 목록을 담은 브레인덤프 완료 응답."""

    status: Literal["completed"] = "completed"
    result: BrainDumpResult


BrainDumpResponse = Annotated[
    BrainDumpClarificationResponse | BrainDumpCompletedResponse,
    Field(discriminator="status"),
]


class TaskBreakdownResult(BaseModel):
    """첫걸음과 후속 단계로 이루어진 쪼개기 결과."""

    first_step: TodoCandidate | None
    steps: list[TodoCandidate]

    @model_validator(mode="after")
    def _check_first_step_rules(self) -> "TaskBreakdownResult":
        """비어 있지 않은 결과에는 first_step이 있어야 하고 합계 상한을 지킨다."""
        if self.first_step is None and self.steps:
            raise ValueError("first_step 없이 steps만 있을 수 없습니다.")
        if self.first_step is not None and 1 + len(self.steps) > MAX_RESULT_ITEMS:
            raise ValueError(
                f"first_step을 포함한 단계는 {MAX_RESULT_ITEMS}개 이하여야 합니다."
            )
        return self


class TaskBreakdownClarificationResponse(BaseModel):
    """질문 하나가 더 필요한 쪼개기 응답."""

    status: Literal["needs_clarification"] = "needs_clarification"
    question: ClarificationQuestion[TaskBreakdownKey]


class TaskBreakdownCompletedResponse(BaseModel):
    """단계 목록을 담은 쪼개기 완료 응답."""

    status: Literal["completed"] = "completed"
    result: TaskBreakdownResult


TaskBreakdownResponse = Annotated[
    TaskBreakdownClarificationResponse | TaskBreakdownCompletedResponse,
    Field(discriminator="status"),
]


class CandidateModelOutput(BaseModel):
    """모델이 반환한 정리 전의 할 일 후보."""

    model_config = ConfigDict(extra="forbid")

    title: str
    memo: str


class QuestionModelOutput[KeyT](BaseModel):
    """모델이 반환한 구체화 질문."""

    model_config = ConfigDict(extra="forbid")

    key: KeyT
    text: str
    options: list[str]


class BrainDumpResultModelOutput(BaseModel):
    """모델이 반환한 브레인덤프 결과."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateModelOutput]


class BrainDumpClarificationOutput(BaseModel):
    """질문이 필요하다는 브레인덤프 모델 출력."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["needs_clarification"]
    question: QuestionModelOutput[BrainDumpKey]


class BrainDumpCompletedOutput(BaseModel):
    """후보 생성을 마쳤다는 브레인덤프 모델 출력."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"]
    result: BrainDumpResultModelOutput


# OpenAI structured output이 oneOf를 지원하지 않아 discriminator 없는 union으로 둔다.
# status Literal과 extra="forbid"가 question·result의 동시 존재를 막는다(5.5 규칙).
BrainDumpModelOutput = BrainDumpClarificationOutput | BrainDumpCompletedOutput


class TaskBreakdownResultModelOutput(BaseModel):
    """모델이 반환한 쪼개기 결과."""

    model_config = ConfigDict(extra="forbid")

    first_step: CandidateModelOutput | None
    steps: list[CandidateModelOutput]


class TaskBreakdownClarificationOutput(BaseModel):
    """질문이 필요하다는 쪼개기 모델 출력."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["needs_clarification"]
    question: QuestionModelOutput[TaskBreakdownKey]


class TaskBreakdownCompletedOutput(BaseModel):
    """분해를 마쳤다는 쪼개기 모델 출력."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"]
    result: TaskBreakdownResultModelOutput


TaskBreakdownModelOutput = (
    TaskBreakdownClarificationOutput | TaskBreakdownCompletedOutput
)
