"""대화를 일정 시간 보관하는 TTL 인메모리 세션 저장소.

세션은 프로세스 메모리에만 존재하므로 재시작·배포로 사라지며, 사라진 세션은
발급된 적 없는 세션과 같은 `404`가 된다.
"""

import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from app.core.config import settings
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.schemas.task_draft import TaskDraft

TurnRole = Literal["user", "assistant"]

_TOO_MANY_SESSIONS = "too many active sessions"
_TOO_MANY_TURNS = "conversation turn limit exceeded"
_CONVERSATION_TOO_LARGE = "conversation size limit exceeded"


@dataclass
class ConversationTurn:
    """세션에 쌓이는 사용자 발화 또는 서버 응답 하나."""

    role: TurnRole
    text: str


@dataclass
class DecomposeState:
    """쪼개기 대화의 시작 기록과 질문 횟수, 직전 분해 결과."""

    target_title: str
    target_notes: str | None = None
    instruction: str | None = None
    asked_questions: int = 0
    last_items: list[TaskDraft] | None = None


@dataclass
class Session:
    """세션 하나가 보관하는 대화 상태."""

    session_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    decompose: DecomposeState | None = None


@dataclass
class _Entry:
    """저장소가 세션과 함께 들고 있는 만료 시각."""

    session: Session
    expires_at: float


_entries: dict[str, _Entry] = {}
_lock = threading.Lock()


def create_session() -> Session:
    """새 세션을 만들어 만료 시각과 함께 저장한다."""
    session = Session(session_id=str(uuid.uuid4()))
    with _lock:
        _purge_expired()
        if len(_entries) >= settings.max_sessions:
            raise ProtectionLimitError(_TOO_MANY_SESSIONS)
        _store(session)
    return session


def get_session(session_id: str) -> Session:
    """만료되지 않은 세션의 대화 상태를 반환한다."""
    with _lock:
        _purge_expired()
        entry = _entries.get(session_id)
    if entry is None:
        raise SessionNotFoundError(f"ai session not found: {session_id}")
    return deepcopy(entry.session)


def save_session(session: Session) -> None:
    """성공한 요청의 대화 상태를 저장하고 만료 시각을 갱신한다."""
    _check_conversation_limits(session)
    with _lock:
        _purge_expired()
        # 요청을 처리하는 동안 만료됐더라도 이미 성공한 대화는 버리지 않는다.
        _store(session)


def reset_sessions() -> None:
    """보관 중인 세션을 모두 버린다 — 테스트와 재시작 재현에 쓴다."""
    with _lock:
        _entries.clear()


def _store(session: Session) -> None:
    """세션 사본에 새 만료 시각을 붙여 넣는다 — 호출자가 락을 잡아야 한다.

    사본을 두어야 저장하지 않은 요청의 대화 변경이 저장소에 새지 않는다.
    """
    _entries[session.session_id] = _Entry(deepcopy(session), _deadline())


def _deadline() -> float:
    """지금부터 세션 TTL만큼 뒤인 만료 시각을 계산한다."""
    return monotonic() + settings.session_ttl_seconds


def _check_conversation_limits(session: Session) -> None:
    """저장하려는 대화가 턴 수·문자 수 상한을 넘었는지 확인한다."""
    if len(session.turns) > settings.max_session_turns:
        raise ProtectionLimitError(_TOO_MANY_TURNS)
    if sum(len(turn.text) for turn in session.turns) > (
        settings.max_session_conversation_chars
    ):
        raise ProtectionLimitError(_CONVERSATION_TOO_LARGE)


def _purge_expired() -> None:
    """만료된 세션을 지운다 — 호출자가 락을 잡아야 한다."""
    now = monotonic()
    for session_id in [
        session_id for session_id, entry in _entries.items() if entry.expires_at <= now
    ]:
        del _entries[session_id]
