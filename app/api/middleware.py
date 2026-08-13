"""모든 응답과 서버 로그에 요청 추적용 `X-Request-Id`를 싣는 ASGI 미들웨어."""

import logging
import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")

logger = logging.getLogger("app.request")


class RequestIdMiddleware:
    """요청의 `X-Request-Id`를 검증·생성해 요청 상태·응답 헤더·서버 로그에 싣는다."""

    def __init__(self, app: ASGIApp) -> None:
        """감쌀 다음 ASGI 앱을 받는다."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """HTTP 요청만 처리하고, 나머지 scope는 손대지 않고 그대로 넘긴다."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            """응답이 시작될 때 헤더에 요청 ID를 넣고 같은 값을 로그에 남긴다."""
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
                logger.info(
                    "%s %s -> %d %s=%s",
                    scope["method"],
                    scope["path"],
                    message["status"],
                    REQUEST_ID_HEADER,
                    request_id,
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # 미처리 예외의 500은 바깥의 ServerErrorMiddleware가 이 미들웨어를
            # 거치지 않고 보내므로, 헤더를 실은 500을 직접 시작하고 예외는
            # 다시 던져 서버가 기록하게 한다.
            if not response_started:
                response = PlainTextResponse("Internal Server Error", status_code=500)
                await response(scope, receive, send_with_request_id)
            raise


def _resolve_request_id(header_value: str | None) -> str:
    """유효한 요청 헤더 값은 그대로 쓰고, 없거나 패턴을 벗어나면 UUID를 만든다."""
    if header_value and _REQUEST_ID_PATTERN.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())
