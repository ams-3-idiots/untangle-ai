"""`Idempotency-Key`로 성공 응답을 재사용하고 중복 실행을 막는 인메모리 캐시.

같은 키의 요청이 동시에 들어오면 먼저 온 요청만 실행하고 나머지는 그 결과를
기다렸다가 함께 받는다.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import cast

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError

_TOO_MANY_ENTRIES = "too many idempotent requests"


@dataclass
class _Entry:
    """한 키의 실행 상태와, 완료된 경우의 결과·만료 시각."""

    done: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: BaseException | None = None
    expires_at: float = 0.0


_entries: dict[str, _Entry] = {}
_lock = threading.Lock()


def run_idempotent[ResultT](key: str | None, action: Callable[[], ResultT]) -> ResultT:
    """키가 있으면 성공 결과를 공유하고, 없거나 공백이면 매번 실행한다."""
    normalized = key.strip() if key else ""
    if not normalized:
        return action()

    entry, owns_execution = _claim(normalized)
    if not owns_execution:
        entry.done.wait()
        if entry.error is not None:
            raise entry.error
        return cast(ResultT, entry.result)

    try:
        entry.result = action()
    except BaseException as error:
        entry.error = error
        _discard(normalized, entry)
        raise
    else:
        entry.expires_at = _deadline()
    finally:
        # 실패로 빠져나갈 때도 깨워야 기다리던 요청이 같은 오류를 받는다.
        entry.done.set()
    return cast(ResultT, entry.result)


def reset_idempotency() -> None:
    """보관 중인 멱등 응답을 모두 버린다 — 테스트와 재시작 재현에 쓴다."""
    with _lock:
        _entries.clear()


def _claim(key: str) -> tuple[_Entry, bool]:
    """키의 캐시 항목을 찾거나 만들고, 이번 호출이 실행을 맡는지 알려준다."""
    with _lock:
        _purge_expired()
        entry = _entries.get(key)
        if entry is not None:
            if entry.done.is_set():
                entry.expires_at = _deadline()
            return entry, False
        if len(_entries) >= settings.max_idempotency_entries:
            raise ProtectionLimitError(_TOO_MANY_ENTRIES)
        entry = _Entry()
        _entries[key] = entry
        return entry, True


def _discard(key: str, entry: _Entry) -> None:
    """실패한 실행의 항목을 지워 다음 요청이 다시 실행되게 한다."""
    with _lock:
        if _entries.get(key) is entry:
            del _entries[key]


def _deadline() -> float:
    """지금부터 캐시 TTL만큼 뒤인 만료 시각을 계산한다."""
    return monotonic() + settings.idempotency_ttl_seconds


def _purge_expired() -> None:
    """만료된 성공 응답을 지운다 — 호출자가 락을 잡은 상태여야 한다."""
    now = monotonic()
    for key in [
        key
        for key, entry in _entries.items()
        if entry.done.is_set() and entry.expires_at <= now
    ]:
        del _entries[key]
