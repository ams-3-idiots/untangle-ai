"""Idempotency-Key 캐시의 응답 재사용·동시 실행·보호 한도 규칙을 검증한다."""

import threading
from collections.abc import Callable

import pytest

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError
from app.services import idempotency_service


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """캐시의 시계를 테스트가 원하는 만큼 앞으로 돌린다."""
    now = 0.0

    def fake_monotonic() -> float:
        return now

    def move(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(idempotency_service, "monotonic", fake_monotonic)
    return move


class _BlockingAction:
    """풀어줄 때까지 실행 중인 상태로 머물러 동시 요청을 겹치게 하는 가짜 작업."""

    def __init__(self, error: Exception | None = None) -> None:
        """실행을 붙잡아 둘 이벤트와 끝낼 때 낼 결과나 오류를 준비한다."""
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self._error = error

    def __call__(self) -> str:
        """호출을 세고 풀릴 때까지 기다렸다가 결과나 오류를 낸다."""
        self.calls += 1
        self.started.set()
        self.release.wait(2)
        if self._error is not None:
            raise self._error
        return "결과"


def _spawn(
    key: str, action: Callable[[], str], results: list[str], errors: list[Exception]
) -> threading.Thread:
    """멱등 실행을 별도 스레드에서 호출하고 결과나 오류를 모은다."""

    def call() -> None:
        try:
            results.append(idempotency_service.run_idempotent(key, action))
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=call)
    thread.start()
    return thread


def _counting_action(calls: list[int]) -> Callable[[], str]:
    """호출 횟수를 기록하고 매번 다른 결과를 내는 작업을 만든다."""

    def action() -> str:
        calls.append(1)
        return f"결과 {len(calls)}"

    return action


def test_missing_key_runs_action_every_time():
    # 준비: 헤더가 없거나 공백인 두 경우를 이어서 호출한다.
    calls: list[int] = []
    action = _counting_action(calls)

    # 실행
    idempotency_service.run_idempotent(None, action)
    idempotency_service.run_idempotent("   ", action)

    # 확인
    assert len(calls) == 2


def test_same_key_returns_the_first_response():
    action = _counting_action([])

    first = idempotency_service.run_idempotent("key-1", action)
    second = idempotency_service.run_idempotent("key-1", action)

    assert (first, second) == ("결과 1", "결과 1")


def test_same_key_does_not_run_action_again():
    calls: list[int] = []
    action = _counting_action(calls)

    idempotency_service.run_idempotent("key-1", action)
    idempotency_service.run_idempotent("key-1", action)

    assert len(calls) == 1


def test_different_keys_run_separately():
    action = _counting_action([])

    first = idempotency_service.run_idempotent("key-1", action)
    second = idempotency_service.run_idempotent("key-2", action)

    assert (first, second) == ("결과 1", "결과 2")


def test_failed_action_is_not_cached():
    calls: list[int] = []

    def action() -> str:
        calls.append(1)
        raise RuntimeError("실행 실패")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            idempotency_service.run_idempotent("key-1", action)

    assert len(calls) == 2


def test_concurrent_same_key_runs_action_once():
    # 준비: 첫 요청이 실행 중인 동안 같은 키의 두 번째 요청을 겹쳐 넣는다.
    blocking = _BlockingAction()
    first = _spawn("key-1", blocking, [], [])
    blocking.started.wait(2)
    second = _spawn("key-1", blocking, [], [])

    # 실행
    blocking.release.set()
    first.join(2)
    second.join(2)

    # 확인
    assert blocking.calls == 1


def test_concurrent_same_key_returns_the_first_response():
    # 준비: 두 번째 요청에는 자기가 실행하면 결과가 달라질 작업을 준다.
    blocking = _BlockingAction()
    results: list[str] = []
    first = _spawn("key-1", blocking, results, [])
    blocking.started.wait(2)
    second = _spawn("key-1", lambda: "두 번째 결과", results, [])

    blocking.release.set()
    first.join(2)
    second.join(2)

    assert results == ["결과", "결과"]


def test_concurrent_same_key_waits_for_the_first_run():
    # 준비: 두 번째 요청의 작업은 실행되기만 하면 곧바로 끝난다.
    blocking = _BlockingAction()
    first = _spawn("key-1", blocking, [], [])
    blocking.started.wait(2)
    second = _spawn("key-1", lambda: "두 번째 결과", [], [])

    second.join(0.1)
    waited = second.is_alive()

    blocking.release.set()
    first.join(2)
    second.join(2)
    assert waited


def test_concurrent_same_key_shares_the_failure():
    # 준비: 두 번째 요청의 작업은 성공하므로, 오류를 받았다면 첫 실행에서 온 것이다.
    blocking = _BlockingAction(error=RuntimeError("실행 실패"))
    errors: list[Exception] = []
    first = _spawn("key-1", blocking, [], errors)
    blocking.started.wait(2)
    second = _spawn("key-1", lambda: "두 번째 결과", [], errors)

    blocking.release.set()
    first.join(2)
    second.join(2)

    assert [str(error) for error in errors] == ["실행 실패", "실행 실패"]


def test_cached_response_expires_after_ttl(advance: Callable[[float], None]):
    calls: list[int] = []
    action = _counting_action(calls)
    idempotency_service.run_idempotent("key-1", action)

    advance(settings.idempotency_ttl_seconds)
    idempotency_service.run_idempotent("key-1", action)

    assert len(calls) == 2


def test_cache_lifetime_restarts_on_each_use(advance: Callable[[float], None]):
    # 준비: 만료 직전에 한 번 더 써서 수명이 다시 시작되는지 본다.
    calls: list[int] = []
    action = _counting_action(calls)
    idempotency_service.run_idempotent("key-1", action)
    advance(settings.idempotency_ttl_seconds - 1)
    idempotency_service.run_idempotent("key-1", action)

    advance(settings.idempotency_ttl_seconds - 1)
    idempotency_service.run_idempotent("key-1", action)

    assert len(calls) == 1


def test_rejects_new_key_over_cache_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_idempotency_entries", 1)
    idempotency_service.run_idempotent("key-1", lambda: "결과")

    with pytest.raises(ProtectionLimitError):
        idempotency_service.run_idempotent("key-2", lambda: "결과")


def test_expired_entry_frees_room_for_a_new_key(
    monkeypatch: pytest.MonkeyPatch, advance: Callable[[float], None]
):
    monkeypatch.setattr(settings, "max_idempotency_entries", 1)
    idempotency_service.run_idempotent("key-1", lambda: "결과")

    advance(settings.idempotency_ttl_seconds)

    assert idempotency_service.run_idempotent("key-2", lambda: "새 결과") == "새 결과"
