"""도메인 예외와 요청 검증 실패를 ProblemDetail 응답으로 변환하는 핸들러.

`main.py`는 `register_exception_handlers`를 호출해 핸들러를 등록하기만 한다.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions.base import DomainError
from app.schemas.error import ProblemDetail

PROBLEM_MEDIA_TYPE = "application/problem+json"


def _problem_content() -> dict[str, Any]:
    """오류 응답 문서에 넣을 problem+json content 선언을 만든다."""
    return {PROBLEM_MEDIA_TYPE: {"schema": ProblemDetail.model_json_schema()}}


VALIDATION_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {
        "description": "요청 본문의 타입·필수값·형식 검증에 실패했다.",
        "content": _problem_content(),
    }
}
"""요청 본문을 받는 엔드포인트가 `responses`에 합쳐 FastAPI 기본 422 문서를 대체한다."""


def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """도메인 예외를 상태 코드에 맞는 ProblemDetail 응답으로 바꾼다."""
    return _problem_response(
        status=exc.status_code, title=exc.title, detail=exc.message
    )


def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI 기본 422 본문을 필드 경로를 담은 ProblemDetail로 바꾼다."""
    return _problem_response(
        status=422, title="Validation failed", detail=_validation_detail(exc)
    )


def register_exception_handlers(app: FastAPI) -> None:
    """도메인 예외와 요청 검증 실패 핸들러를 애플리케이션에 등록한다."""
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)


def error_responses(*errors: type[DomainError]) -> dict[int, dict[str, Any]]:
    """도메인 예외 목록을 문서화하기 위해 엔드포인트 `responses` 선언으로 변환한다."""
    grouped: dict[int, list[str]] = {}
    for error in errors:
        grouped.setdefault(error.status_code, []).append(error.description)
    return {
        status: {"description": "\n\n".join(docs), "content": _problem_content()}
        for status, docs in grouped.items()
    }


def _validation_detail(exc: RequestValidationError) -> str:
    """검증 오류마다 `"필드경로: 사유"`를 만들어 `"; "`로 연결한다."""
    parts: list[str] = []
    for error in exc.errors():
        message = str(error["msg"])
        # json_invalid의 loc은 필드 경로가 아니라 파서의 문자 위치라 경로를 뺀다.
        if error.get("type") == "json_invalid":
            parts.append(message)
            continue
        location = [str(item) for item in error["loc"]]
        if location and location[0] == "body":
            location = location[1:]
        path = ".".join(location)
        parts.append(f"{path}: {message}" if path else message)
    return "; ".join(parts)


def _problem_response(status: int, title: str, detail: str) -> JSONResponse:
    """ProblemDetail 본문과 전용 media type을 가진 JSON 응답을 만든다."""
    problem = ProblemDetail(title=title, status=status, detail=detail)
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(),
        media_type=PROBLEM_MEDIA_TYPE,
    )
