"""AI 기능이 발생시키는 도메인 예외를 정의한다."""

from app.exceptions.base import DomainError

AI_UNAVAILABLE_MESSAGE = "AI 응답을 가져오지 못했습니다. 잠시 후 다시 시도해주세요."
"""provider 경계에서 나는 503의 고정 detail — 실패 원인을 응답으로 알리지 않는다."""


class InvalidClarificationStateError(DomainError):
    """중복 key나 질문 한도를 넘긴 구체화 이력으로 요청한 상태."""

    status_code = 400
    title = "Bad request"
    description = "구체화 이력에 중복 key가 있거나 질문 한도를 넘었다."


class AINotConfiguredError(DomainError):
    """OpenAI key·model 설정이 없어 AI 기능을 쓸 수 없는 상태."""

    status_code = 503
    title = "AI service unavailable"
    description = "AI 기능이 설정되지 않아 요청을 처리할 수 없다."


class AIProviderError(DomainError):
    """timeout·네트워크 등으로 OpenAI 호출 자체가 실패한 상태."""

    status_code = 503
    title = "AI service unavailable"
    description = "LLM 호출이 실패했다."


class InvalidAIResponseError(DomainError):
    """정식 schema나 질문 이력 규칙을 어긴 모델 응답을 받은 상태."""

    status_code = 503
    title = "AI service unavailable"
    description = "형식이나 질문 이력 규칙을 어긴 AI 응답을 받았다."
