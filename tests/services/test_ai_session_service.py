"""브레인덤프의 결과 정규화·중복 제거와 세션 수명 규칙을 검증한다."""

from collections.abc import Callable

import pytest

from app.core.config import settings
from app.exceptions.ai import (
    AI_UNAVAILABLE_MESSAGE,
    AIProviderError,
    InvalidAIResponseError,
)
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.schemas.ai_session import DumpModelOutput, DumpRequest
from app.services import ai_session_service, session_service

DUMP_TEXT = "졸업논문 중간발표가 2주 뒤인데 아직 데이터 정리도 안 했어."

_EMPTY_TASK = {
    "title": "",
    "memo": None,
    "importance": None,
    "estimated_minutes": None,
    "due_date": None,
    "due_time": None,
    "reminder_minutes_before": None,
    "source_excerpt": None,
}


def _model_output(
    tasks: list[dict], assistant_text: str = "일단 눈에 보이는 것부터 나눠봤어요."
) -> DumpModelOutput:
    """모델이 반환한 덤프 결과를 만든다 — 적지 않은 필드는 null로 채운다."""
    return DumpModelOutput.model_validate(
        {
            "tasks": [_EMPTY_TASK | task for task in tasks],
            "assistant_text": assistant_text,
        }
    )


def _request(
    text: str = DUMP_TEXT, existing_task_titles: list[str] | None = None
) -> DumpRequest:
    """덤프 요청 DTO를 만든다."""
    return DumpRequest(text=text, existing_task_titles=existing_task_titles or [])


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """세션 저장소의 시계를 테스트가 원하는 만큼 앞으로 돌린다."""
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


@pytest.fixture
def live_session_id() -> str:
    """덤프에 사용할 살아 있는 세션의 식별자를 만든다."""
    return ai_session_service.create_session().session_id


def test_proposal_id_matches_session_id(fake_llm, live_session_id: str):
    # 준비
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))

    # 실행
    response = ai_session_service.run_dump(live_session_id, _request())

    # 확인
    assert response.proposal_id == live_session_id


def test_run_dump_rejects_unissued_session(fake_llm):
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))

    with pytest.raises(SessionNotFoundError):
        ai_session_service.run_dump("발급된-적-없는-세션", _request())


def test_run_dump_checks_rate_limit(
    fake_llm, live_session_id: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "rate_limit_requests", 0)
    fake_llm(AssertionError("LLM은 호출되면 안 된다"))

    with pytest.raises(ProtectionLimitError):
        ai_session_service.run_dump(live_session_id, _request())


def test_nullifies_out_of_range_importance(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": "논문 데이터 정리하기", "importance": 4}]))

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].importance is None


def test_nullifies_non_positive_estimated_minutes(fake_llm, live_session_id: str):
    fake_llm(
        _model_output([{"title": "논문 데이터 정리하기", "estimated_minutes": -5}])
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].estimated_minutes is None


def test_nullifies_empty_memo(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": "논문 데이터 정리하기", "memo": ""}]))

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].memo is None


def test_keeps_source_excerpt_copied_from_text(fake_llm, live_session_id: str):
    fake_llm(
        _model_output(
            [{"title": "논문 데이터 정리하기", "source_excerpt": "아직 데이터 정리도"}]
        )
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].source_excerpt == "아직 데이터 정리도"


def test_trims_source_excerpt_before_matching(fake_llm, live_session_id: str):
    fake_llm(
        _model_output(
            [
                {
                    "title": "논문 데이터 정리하기",
                    "source_excerpt": "  아직 데이터 정리도 ",
                }
            ]
        )
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].source_excerpt == "아직 데이터 정리도"


def test_nullifies_source_excerpt_missing_from_text(fake_llm, live_session_id: str):
    # 준비: 모델이 입력에 없는 문장을 근거로 지어낸 상황이다.
    fake_llm(
        _model_output(
            [
                {
                    "title": "논문 데이터 정리하기",
                    "source_excerpt": "지도교수님이 재촉했어",
                }
            ]
        )
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].source_excerpt is None


def test_nullifies_empty_source_excerpt(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": "논문 데이터 정리하기", "source_excerpt": "  "}]))

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks[0].source_excerpt is None


def test_drops_task_already_in_existing_titles(fake_llm, live_session_id: str):
    fake_llm(
        _model_output(
            [{"title": " 교수님 미팅 준비 "}, {"title": "논문 데이터 정리하기"}]
        )
    )

    response = ai_session_service.run_dump(
        live_session_id, _request(existing_task_titles=["교수님 미팅 준비"])
    )

    assert [task.title for task in response.tasks] == ["논문 데이터 정리하기"]


def test_drops_existing_title_ignoring_letter_case(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": "Send Mail"}]))

    response = ai_session_service.run_dump(
        live_session_id, _request(existing_task_titles=["send mail"])
    )

    assert response.tasks == []


def test_keeps_first_of_duplicate_titles(fake_llm, live_session_id: str):
    fake_llm(
        _model_output(
            [
                {"title": "논문 데이터 정리하기", "memo": "첫 항목"},
                {"title": " 논문 데이터 정리하기 ", "memo": "중복"},
            ]
        )
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert [task.memo for task in response.tasks] == ["첫 항목"]


def test_keeps_at_most_five_tasks(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": f"할 일 {index}"} for index in range(7)]))

    response = ai_session_service.run_dump(live_session_id, _request())

    assert len(response.tasks) == 5


def test_counts_five_tasks_after_removing_existing_titles(
    fake_llm, live_session_id: str
):
    # 준비: 중복을 걷어내기 전에 상한을 적용하면 후보가 5개보다 적어진다.
    fake_llm(_model_output([{"title": f"할 일 {index}"} for index in range(7)]))

    response = ai_session_service.run_dump(
        live_session_id, _request(existing_task_titles=["할 일 0", "할 일 1"])
    )

    assert len(response.tasks) == 5


def test_returns_empty_tasks_when_model_finds_none(fake_llm, live_session_id: str):
    fake_llm(
        _model_output([], assistant_text="어떤 일이 남았는지 조금만 더 적어줄래요?")
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.tasks == []


def test_strips_assistant_text(fake_llm, live_session_id: str):
    fake_llm(
        _model_output(
            [{"title": "논문 데이터 정리하기"}], assistant_text=" 나눠봤어요. "
        )
    )

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.assistant_text == "나눠봤어요."


def test_keeps_empty_assistant_text_when_tasks_exist(fake_llm, live_session_id: str):
    # 준비: 안내 문구는 후보가 있을 때만 비어 있어도 된다.
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}], assistant_text="   "))

    response = ai_session_service.run_dump(live_session_id, _request())

    assert response.assistant_text == ""


def test_rejects_model_response_without_task_and_guidance(
    fake_llm, live_session_id: str
):
    fake_llm(_model_output([], assistant_text="   "))

    with pytest.raises(InvalidAIResponseError):
        ai_session_service.run_dump(live_session_id, _request())


def test_rejects_model_response_with_impossible_due_date(
    fake_llm, live_session_id: str
):
    fake_llm(
        _model_output([{"title": "논문 데이터 정리하기", "due_date": "2026-13-40"}])
    )

    with pytest.raises(InvalidAIResponseError):
        ai_session_service.run_dump(live_session_id, _request())


def test_rejects_model_response_with_malformed_due_time(fake_llm, live_session_id: str):
    fake_llm(_model_output([{"title": "논문 데이터 정리하기", "due_time": "오후 6시"}]))

    with pytest.raises(InvalidAIResponseError):
        ai_session_service.run_dump(live_session_id, _request())


def test_run_dump_extends_session_lifetime(fake_llm, advance: Callable[[float], None]):
    # 준비: 만료 직전에 성공한 덤프가 세션 수명을 다시 늘리는지 본다.
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))
    session_id = ai_session_service.create_session().session_id
    advance(settings.session_ttl_seconds - 1)
    ai_session_service.run_dump(session_id, _request())

    advance(settings.session_ttl_seconds - 1)

    assert ai_session_service.run_dump(session_id, _request()).proposal_id == session_id


def test_reused_response_extends_session_lifetime(
    fake_llm, advance: Callable[[float], None]
):
    # 준비: 같은 키로만 재시도하는 앱의 세션이 캐시 때문에 만료되면 안 된다.
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))
    session_id = ai_session_service.create_session().session_id
    ai_session_service.run_dump(session_id, _request(), "retry-1")
    advance(settings.session_ttl_seconds - 1)
    ai_session_service.run_dump(session_id, _request(), "retry-1")

    advance(settings.session_ttl_seconds - 1)

    assert ai_session_service.run_dump(session_id, _request()).proposal_id == session_id


def test_dump_does_not_pile_up_conversation_turns(fake_llm, live_session_id: str):
    # 준비: 덤프가 대화를 쌓으면 긴 세션이 턴·크기 한도에 걸려 429가 된다.
    fake_llm(_model_output([{"title": "논문 데이터 정리하기"}]))

    ai_session_service.run_dump(live_session_id, _request())

    assert session_service.get_session(live_session_id).turns == []


def test_failed_dump_does_not_extend_session_lifetime(
    fake_llm, advance: Callable[[float], None]
):
    fake_llm(AIProviderError(AI_UNAVAILABLE_MESSAGE))
    session_id = ai_session_service.create_session().session_id
    advance(settings.session_ttl_seconds - 1)
    with pytest.raises(AIProviderError):
        ai_session_service.run_dump(session_id, _request())

    advance(1)

    with pytest.raises(SessionNotFoundError):
        ai_session_service.run_dump(session_id, _request())
