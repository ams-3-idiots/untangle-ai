"""프로세스 단위 LLM 요청 rate limit의 구간 규칙을 검증한다."""

from collections.abc import Callable

import pytest

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError
from app.services import rate_limit_service


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """rate limit의 시계를 테스트가 원하는 만큼 앞으로 돌린다."""
    now = 0.0

    def fake_monotonic() -> float:
        return now

    def move(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(rate_limit_service, "monotonic", fake_monotonic)
    return move


def test_allows_requests_up_to_the_limit(monkeypatch: pytest.MonkeyPatch):
    # 준비: 한도를 2로 낮춰 경계를 짧게 확인한다.
    monkeypatch.setattr(settings, "rate_limit_requests", 2)

    # 실행
    rate_limit_service.check_rate_limit()
    rate_limit_service.check_rate_limit()

    # 확인: 한도까지는 예외 없이 통과한다.


def test_rejects_request_over_the_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    rate_limit_service.check_rate_limit()
    rate_limit_service.check_rate_limit()

    with pytest.raises(ProtectionLimitError):
        rate_limit_service.check_rate_limit()


def test_allows_again_after_the_window_passes(
    monkeypatch: pytest.MonkeyPatch, advance: Callable[[float], None]
):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    rate_limit_service.check_rate_limit()

    advance(settings.rate_limit_window_seconds)
    rate_limit_service.check_rate_limit()


def test_still_rejects_inside_the_window(
    monkeypatch: pytest.MonkeyPatch, advance: Callable[[float], None]
):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    rate_limit_service.check_rate_limit()

    advance(settings.rate_limit_window_seconds - 1)

    with pytest.raises(ProtectionLimitError):
        rate_limit_service.check_rate_limit()
