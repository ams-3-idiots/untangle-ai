"""프로세스 보호 한도 초과 예외를 정의한다."""

from app.exceptions.base import DomainError


class ProtectionLimitError(DomainError):
    """세션·대화·멱등 응답 캐시 용량이나 rate limit을 넘어선 상태."""

    status_code = 429
    title = "Too many requests"
    description = "세션·대화·응답 캐시 용량이나 요청 빈도 한도를 넘었다."
