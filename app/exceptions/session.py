"""세션 기능이 발생시키는 도메인 예외를 정의한다."""

from app.exceptions.base import DomainError


class SessionNotFoundError(DomainError):
    """만료·미발급·프로세스 재시작 중 어느 이유로든 세션을 찾지 못한 상태."""

    status_code = 404
    title = "Not found"
    description = "세션이 없거나 만료돼 대화를 이어갈 수 없다."
