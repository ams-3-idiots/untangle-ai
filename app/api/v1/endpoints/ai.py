"""AI 브레인덤프·할 일 쪼개기 엔드포인트를 제공한다."""

from fastapi import APIRouter

from app.exceptions.ai import (
    AINotConfiguredError,
    AIProviderError,
    InvalidAIResponseError,
    InvalidClarificationStateError,
)
from app.exceptions.handlers import error_responses
from app.schemas.ai import (
    BrainDumpRequest,
    BrainDumpResponse,
    TaskBreakdownRequest,
    TaskBreakdownResponse,
)
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])

AI_ERROR_RESPONSES = error_responses(
    InvalidClarificationStateError,
    AIProviderError,
    InvalidAIResponseError,
    AINotConfiguredError,
)


@router.post(
    "/brain-dump",
    response_model=BrainDumpResponse,
    summary="브레인덤프에서 할 일 후보를 뽑는다",
    responses=AI_ERROR_RESPONSES,
)
def run_brain_dump(payload: BrainDumpRequest) -> BrainDumpResponse:
    """정보가 부족하면 질문 하나를, 충분하면 후보 목록을 반환한다.

    앱은 서버가 준 질문과 답변을 `clarifications`에 누적해 다시 호출한다.
    질문은 최대 1번만 온다.
    """
    return ai_service.run_brain_dump(payload)


@router.post(
    "/task-breakdown",
    response_model=TaskBreakdownResponse,
    summary="목표 한 줄을 실행 단계로 쪼갠다",
    responses=AI_ERROR_RESPONSES,
)
def run_task_breakdown(payload: TaskBreakdownRequest) -> TaskBreakdownResponse:
    """정보가 부족하면 질문 하나를, 충분하면 첫걸음과 후속 단계를 반환한다.

    앱은 서버가 준 질문과 답변을 `clarifications`에 누적해 다시 호출한다.
    질문은 최대 3번까지 올 수 있다.
    """
    return ai_service.run_task_breakdown(payload)
