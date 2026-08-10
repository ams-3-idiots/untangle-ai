"""AI 기능이 발생시키는 도메인 예외를 정의한다."""

from app.exceptions.base import DomainError


class InvalidClarificationStateError(DomainError):
    """중복 key나 질문 한도를 넘긴 구체화 이력으로 요청한 상태."""

    status_code = 422
    code = "invalid_clarification_state"


class AINotConfiguredError(DomainError):
    """OpenAI key·model 설정이 없어 AI 기능을 쓸 수 없는 상태."""

    status_code = 503
    code = "ai_not_configured"


class AIProviderError(DomainError):
    """timeout·네트워크 등으로 OpenAI 호출 자체가 실패한 상태."""

    status_code = 502
    code = "ai_provider_error"


class InvalidAIResponseError(DomainError):
    """정식 schema나 질문 이력 규칙을 어긴 모델 응답을 받은 상태."""

    status_code = 502
    code = "invalid_ai_response"
