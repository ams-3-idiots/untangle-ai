"""AI 세션 생성과 브레인덤프 엔드포인트를 제공한다."""

from typing import Annotated

from fastapi import APIRouter, Header, Path

from app.exceptions.ai import (
    AINotConfiguredError,
    AIProviderError,
    InvalidAIResponseError,
)
from app.exceptions.handlers import VALIDATION_ERROR_RESPONSES, error_responses
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.schemas.ai_session import DumpRequest, DumpResponse, SessionCreatedResponse
from app.services import ai_session_service

router = APIRouter(prefix="/ai-sessions", tags=["ai-sessions"])

SessionIdPath = Annotated[
    str, Path(alias="sessionId", description="세션 생성 API가 발급한 세션 식별자")
]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="재시도를 같은 요청으로 묶는 키. 없으면 매번 새로 처리한다",
    ),
]

SESSION_ERROR_RESPONSES = error_responses(ProtectionLimitError)

DUMP_ERROR_RESPONSES = {
    **error_responses(
        SessionNotFoundError,
        ProtectionLimitError,
        AINotConfiguredError,
        AIProviderError,
        InvalidAIResponseError,
    ),
    **VALIDATION_ERROR_RESPONSES,
}


@router.post(
    "",
    response_model=SessionCreatedResponse,
    status_code=201,
    summary="AI 대화 세션을 만든다",
    responses=SESSION_ERROR_RESPONSES,
)
def create_ai_session() -> SessionCreatedResponse:
    """본문 없이 호출하며, 받은 `sessionId`를 이후 요청 경로에 싣는다."""
    return ai_session_service.create_session()


@router.post(
    "/{sessionId}/dump",
    response_model=DumpResponse,
    summary="브레인덤프에서 할 일 후보를 뽑는다",
    responses=DUMP_ERROR_RESPONSES,
)
def run_dump(
    session_id: SessionIdPath,
    payload: DumpRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> DumpResponse:
    """만료됐거나 발급된 적 없는 세션은 `404`로 응답한다.

    뽑을 후보가 없으면 빈 `tasks`와 재입력 안내를 담아 `200`으로 응답한다.
    """
    return ai_session_service.run_dump(session_id, payload, idempotency_key)
