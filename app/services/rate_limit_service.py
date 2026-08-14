"""프로세스가 받는 LLM 요청 수를 시간 구간 단위로 제한한다.

사용자 개념이 없으므로 한도는 사용자별이 아니라 프로세스 전체에 걸린다.
"""

import threading
from collections import deque
from time import monotonic

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError

_TOO_MANY_REQUESTS = "too many requests"

_hits: deque[float] = deque()
_lock = threading.Lock()


def check_rate_limit() -> None:
    """이번 LLM 요청을 기록하고, 구간 한도를 넘었으면 거절한다."""
    with _lock:
        now = monotonic()
        window_start = now - settings.rate_limit_window_seconds
        while _hits and _hits[0] <= window_start:
            _hits.popleft()
        if len(_hits) >= settings.rate_limit_requests:
            raise ProtectionLimitError(_TOO_MANY_REQUESTS)
        _hits.append(now)


def reset_rate_limit() -> None:
    """기록된 요청 시각을 모두 버린다 — 테스트와 재시작 재현에 쓴다."""
    with _lock:
        _hits.clear()
