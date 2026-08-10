"""도메인 예외가 변환된 공통 오류 응답 형식."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """`exceptions/handlers.py`가 반환하는 공통 오류 본문."""

    code: str = Field(description="오류 종류를 구분하는 코드")
    message: str = Field(description="사용자에게 보여줄 수 있는 설명")
