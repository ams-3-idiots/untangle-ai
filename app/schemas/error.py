"""도메인 예외와 요청 검증 실패가 변환되는 공통 오류 응답 형식."""

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """모든 오류 응답이 공유하는 RFC 9457 본문."""

    type: str = Field(
        default="about:blank", description="문제 유형 URI. 항상 `about:blank`"
    )
    title: str = Field(description="상태 코드별로 고정된 오류 제목")
    status: int = Field(description="HTTP 상태 코드와 같은 값")
    detail: str = Field(description="사람이 읽는 오류 설명")
