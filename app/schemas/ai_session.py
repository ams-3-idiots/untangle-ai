"""AI 세션 생성과 브레인덤프의 요청·응답 형식과 모델 출력 형식을 정의한다."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.base import CamelModel
from app.schemas.task_draft import TaskDraft

MAX_DUMP_TASKS = 5
"""덤프 응답이 담을 수 있는 할 일 후보 수 상한."""

MAX_EXISTING_TASK_TITLES = 200
"""중복 판단 기준으로 한 번에 받을 수 있는 기존 할 일 제목 수 상한."""

DumpTextStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)
]
ExistingTaskTitleStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500)
]
ClientNowStr = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


class SessionCreatedResponse(CamelModel):
    """세션 생성 응답: 이후 요청 경로에 실을 세션 식별자."""

    session_id: str = Field(description="덤프 요청 경로에 실어 보낼 세션 식별자")


class DumpRequest(CamelModel):
    """브레인덤프 요청: 정리되지 않은 원문과 중복 판단에 쓸 기존 할 일 제목."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "졸업논문 중간발표가 2주 뒤인데 아직 데이터 정리도 안 했고"
                        " 교수님 미팅도 다시 잡아야 해."
                    ),
                    "existingTaskTitles": ["교수님 미팅 준비"],
                    "clientNow": "2026-07-09T22:00:00+09:00",
                }
            ]
        }
    )

    text: DumpTextStr = Field(description="할 일을 추출할, 사용자가 쏟아낸 생각 뭉치")
    existing_task_titles: list[ExistingTaskTitleStr] = Field(
        max_length=MAX_EXISTING_TASK_TITLES,
        description="앱에 이미 있는 할 일 제목. 같은 제목은 후보로 만들지 않는다",
    )
    client_now: ClientNowStr | None = Field(
        default=None,
        description=(
            "앱 로컬 현재 시각. 상대 기한을 환산하는 기준이며 형식은 검증하지 않는다"
        ),
    )


class DumpResponse(CamelModel):
    """브레인덤프 응답: 할 일 후보와 사용자에게 보여줄 안내 문구."""

    proposal_id: str = Field(
        description="제안을 식별하는 값. 경로의 `sessionId`와 항상 같다"
    )
    tasks: list[TaskDraft] = Field(
        max_length=MAX_DUMP_TASKS,
        description="할 일 후보. 뽑을 후보가 없으면 빈 배열이며 오류가 아니다",
    )
    assistant_text: str = Field(
        description="결과 안내 문구. `tasks`가 비면 무엇을 더 적으면 좋을지 안내한다"
    )


class DumpTaskModelOutput(BaseModel):
    """모델이 반환한 정리 전의 할 일 후보 한 건."""

    model_config = ConfigDict(extra="forbid")

    title: str
    memo: str | None
    importance: int | None
    # 모델이 소수로 답해도 정규화가 정수로 줄이도록 float으로 받는다.
    estimated_minutes: float | None
    due_date: str | None
    due_time: str | None
    reminder_minutes_before: int | None
    source_excerpt: str | None


class DumpModelOutput(BaseModel):
    """모델이 반환한 정리 전의 브레인덤프 결과."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[DumpTaskModelOutput]
    assistant_text: str
