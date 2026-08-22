"""TTL 인메모리 세션 저장소의 수명·복원·보호 한도 규칙을 검증한다."""

from collections.abc import Callable

import pytest

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.schemas.task_draft import TaskDraft
from app.services import session_service
from app.services.session_service import ConversationTurn, DecomposeState


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """저장소의 시계를 테스트가 원하는 만큼 앞으로 돌린다."""
    now = 0.0

    def fake_monotonic() -> float:
        """테스트가 제어하는 현재 시각을 반환한다."""
        return now

    def move(seconds: float) -> None:
        """테스트 시각을 지정한 초만큼 앞으로 옮긴다."""
        nonlocal now
        now += seconds

    monkeypatch.setattr(session_service, "monotonic", fake_monotonic)
    return move


def _turn(text: str) -> ConversationTurn:
    """사용자 발화 한 턴을 만든다."""
    return ConversationTurn(role="user", text=text)


def test_create_session_issues_unique_ids():
    # 준비: 이 테스트에는 별도의 요청 데이터가 없다.

    # 실행
    first = session_service.create_session()
    second = session_service.create_session()

    # 확인
    assert first.session_id != second.session_id


def test_get_session_returns_created_session():
    created = session_service.create_session()

    found = session_service.get_session(created.session_id)

    assert found.session_id == created.session_id


def test_get_session_rejects_unissued_id():
    with pytest.raises(SessionNotFoundError):
        session_service.get_session("발급된-적-없는-세션")


def test_not_found_detail_includes_session_id():
    with pytest.raises(SessionNotFoundError) as raised:
        session_service.get_session("cace6837")

    assert raised.value.message == "ai session not found: cace6837"


def test_get_session_rejects_expired_session(advance: Callable[[float], None]):
    created = session_service.create_session()

    advance(settings.session_ttl_seconds)

    with pytest.raises(SessionNotFoundError):
        session_service.get_session(created.session_id)


def test_get_session_alone_does_not_extend_lifetime(
    advance: Callable[[float], None],
):
    # 준비: 만료 직전에 조회만 하고 저장은 하지 않는다.
    created = session_service.create_session()
    advance(settings.session_ttl_seconds - 1)
    session_service.get_session(created.session_id)

    advance(1)

    with pytest.raises(SessionNotFoundError):
        session_service.get_session(created.session_id)


def test_save_session_extends_lifetime(advance: Callable[[float], None]):
    created = session_service.create_session()
    advance(settings.session_ttl_seconds - 1)

    session_service.save_session(created)
    advance(settings.session_ttl_seconds - 1)

    assert session_service.get_session(created.session_id).session_id == (
        created.session_id
    )


def test_saved_conversation_is_restored():
    created = session_service.create_session()
    created.turns.append(_turn("운동을 시작하고 싶어"))

    session_service.save_session(created)

    restored = session_service.get_session(created.session_id)
    assert [turn.text for turn in restored.turns] == ["운동을 시작하고 싶어"]


def test_saved_decompose_state_is_restored():
    created = session_service.create_session()
    created.decompose = DecomposeState(
        target_title="운동 시작하기",
        last_items=[TaskDraft(title="운동화 꺼내기")],
    )

    session_service.save_session(created)

    restored = session_service.get_session(created.session_id)
    assert restored.decompose.target_title == "운동 시작하기"
    assert [item.title for item in restored.decompose.last_items] == ["운동화 꺼내기"]


def test_unsaved_conversation_change_does_not_reach_storage():
    # 준비: 요청이 실패해 저장하지 않은 상황을 대화만 바꾸고 끝내 재현한다.
    created = session_service.create_session()
    loaded = session_service.get_session(created.session_id)

    loaded.turns.append(_turn("실패한 요청의 발화"))

    assert session_service.get_session(created.session_id).turns == []


def test_reset_sessions_makes_existing_session_not_found():
    created = session_service.create_session()

    session_service.reset_sessions()

    with pytest.raises(SessionNotFoundError):
        session_service.get_session(created.session_id)


def test_create_session_rejects_request_over_session_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "max_sessions", 1)
    session_service.create_session()

    with pytest.raises(ProtectionLimitError):
        session_service.create_session()


def test_expired_session_frees_room_for_a_new_one(
    monkeypatch: pytest.MonkeyPatch, advance: Callable[[float], None]
):
    monkeypatch.setattr(settings, "max_sessions", 1)
    session_service.create_session()

    advance(settings.session_ttl_seconds)

    assert session_service.create_session().session_id


def test_save_session_rejects_conversation_over_turn_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "max_session_turns", 2)
    created = session_service.create_session()
    created.turns.extend(_turn(f"발화 {index}") for index in range(3))

    with pytest.raises(ProtectionLimitError):
        session_service.save_session(created)


def test_save_session_rejects_conversation_over_size_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "max_session_conversation_chars", 5)
    created = session_service.create_session()
    created.turns.append(_turn("여섯 글자가 넘는 발화"))

    with pytest.raises(ProtectionLimitError):
        session_service.save_session(created)


def test_rejected_conversation_is_not_stored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "max_session_turns", 1)
    created = session_service.create_session()
    created.turns.extend(_turn(f"발화 {index}") for index in range(2))

    with pytest.raises(ProtectionLimitError):
        session_service.save_session(created)

    assert session_service.get_session(created.session_id).turns == []
