"""도메인 예외의 공통 베이스.

`services`는 여기서 파생된 예외만 발생시키고 `HTTPException`을 사용하지 않는다.
HTTP 응답으로의 변환은 `exceptions/handlers.py`가 담당한다.
"""


class DomainError(Exception):
    """업무 규칙 위반을 나타내는 예외.

    하위 클래스는 `status_code`와 `code`를 재정의해 어떤 HTTP 응답으로 바뀔지 정한다.
    """

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
