"""도메인 예외를 HTTP 응답으로 변환하는 핸들러.

`main.py`는 `register_exception_handlers`를 호출해 핸들러를 등록하기만 한다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions.base import DomainError


def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
