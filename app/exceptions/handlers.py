"""도메인 예외를 HTTP 응답으로 변환하는 핸들러.

`main.py`는 `register_exception_handlers`를 호출해 핸들러를 등록하기만 한다.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions.base import DomainError
from app.schemas.error import ErrorResponse


def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """도메인 예외를 공통 오류 본문의 JSON 응답으로 바꾼다."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """도메인 예외 핸들러를 애플리케이션에 등록한다."""
    app.add_exception_handler(DomainError, domain_error_handler)


def error_responses(*errors: type[DomainError]) -> dict[int, dict[str, Any]]:
    """도메인 예외 목록을 문서화하기 위해 엔드포인트 `responses` 선언으로 변환한다."""
    grouped: dict[int, list[str]] = {}
    for error in errors:
        grouped.setdefault(error.status_code, []).append(error.description)
    return {
        status: {"model": ErrorResponse, "description": "\n\n".join(docs)}
        for status, docs in grouped.items()
    }
