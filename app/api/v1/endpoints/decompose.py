"""Spring 호환 할 일 쪼개기 대화 엔드포인트를 제공한다."""

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
from app.schemas.decompose import (
    DecomposeMessageRequest,
    DecomposeResponse,
    DecomposeStartRequest,
)
from app.services import decompose_service

router = APIRouter(prefix="/ai-sessions", tags=["decompose"])

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="재시도가 저장된 성공 응답을 그대로 받게 하는 선택 헤더",
    ),
]
SessionId = Annotated[
    str, Path(alias="sessionId", description="쪼개기 시작 응답이 준 `sessionId`")
]

_AI_ERROR_RESPONSES = error_responses(
    ProtectionLimitError,
    AIProviderError,
    InvalidAIResponseError,
    AINotConfiguredError,
)
START_ERROR_RESPONSES = {**_AI_ERROR_RESPONSES, **VALIDATION_ERROR_RESPONSES}
CONTINUE_ERROR_RESPONSES = {
    **error_responses(SessionNotFoundError),
    **START_ERROR_RESPONSES,
}


@router.post(
    "/decompose",
    response_model=DecomposeResponse,
    status_code=201,
    summary="할 일 쪼개기 대화를 시작한다",
    responses=START_ERROR_RESPONSES,
)
def start_decompose(
    payload: DecomposeStartRequest, idempotency_key: IdempotencyKey = None
) -> DecomposeResponse:
    """세션을 함께 만들어 첫 응답을 돌려주므로 별도의 세션 생성이 필요 없다.

    `items`가 null이면 질문 턴이고, 응답의 `sessionId`로 이어가기를 호출한다.
    """
    return decompose_service.start_decompose(payload, idempotency_key)


@router.post(
    "/{sessionId}/decompose",
    response_model=DecomposeResponse,
    summary="쪼개기 대화를 이어간다",
    responses=CONTINUE_ERROR_RESPONSES,
)
def continue_decompose(
    session_id: SessionId,
    payload: DecomposeMessageRequest,
    idempotency_key: IdempotencyKey = None,
) -> DecomposeResponse:
    """서버가 대화를 기억하므로 앱은 이번 발화 하나만 보낸다.

    쪼개기 시작으로 만들어진 세션에서만 동작하며, 그 밖의 세션은 `404`다.
    """
    return decompose_service.continue_decompose(session_id, payload, idempotency_key)
