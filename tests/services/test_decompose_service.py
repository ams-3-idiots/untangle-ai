"""쪼개기 대화의 턴 전환, 대화 복원과 결과 정규화 규칙을 검증한다."""

from collections.abc import Callable

import pytest

from app.core.config import settings
from app.exceptions.ai import AIProviderError, InvalidAIResponseError
from app.exceptions.limit import ProtectionLimitError
from app.exceptions.session import SessionNotFoundError
from app.schemas.decompose import (
    DecomposeItemModelOutput,
    DecomposeMessageRequest,
    DecomposeModelOutput,
    DecomposeResponse,
    DecomposeStartRequest,
    DecomposeTarget,
)
from app.services import decompose_service, session_service

TARGET_TITLE = "운동 시작하기"


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """세션 저장소의 시계를 테스트가 원하는 만큼 앞으로 돌린다."""
    now = 0.0

    def fake_monotonic() -> float:
        return now

    def move(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(session_service, "monotonic", fake_monotonic)
    return move


def _item(
    title: str, importance: int | None = 2, estimated_minutes: int | None = 10
) -> DecomposeItemModelOutput:
    """모델이 반환한 단계 한 건을 만든다."""
    return DecomposeItemModelOutput(
        title=title, importance=importance, estimated_minutes=estimated_minutes
    )


def _question(
    text: str = "운동을 시작하려는 주된 목적이 뭔가요?",
    options: list[str] | None = None,
) -> DecomposeModelOutput:
    """질문 턴 모델 출력을 만든다."""
    return DecomposeModelOutput(
        needs_clarification=True,
        assistant_text=text,
        options=["체중 감량", "체력 증진"] if options is None else options,
        items=[],
        first_step=None,
    )


def _decomposition(
    *titles: str,
    first_step: DecomposeItemModelOutput | None = None,
    assistant_text: str = "가볍게 시작할 수 있게 나눴어요.",
) -> DecomposeModelOutput:
    """분해 턴 모델 출력을 만든다."""
    return DecomposeModelOutput(
        needs_clarification=False,
        assistant_text=assistant_text,
        options=[],
        items=[_item(title) for title in titles],
        first_step=first_step,
    )


def _start(
    title: str = TARGET_TITLE, notes: str | None = None, instruction: str | None = None
) -> DecomposeResponse:
    """쪼개기 시작을 호출한다."""
    return decompose_service.start_decompose(
        DecomposeStartRequest(
            target=DecomposeTarget(title=title, notes=notes), instruction=instruction
        )
    )


def _continue(
    session_id: str, message: str = "체력 증진이 목적이야"
) -> DecomposeResponse:
    """쪼개기 이어가기를 호출한다."""
    return decompose_service.continue_decompose(
        session_id, DecomposeMessageRequest(message=message)
    )


def test_start_returns_question_turn_with_null_items(fake_llm):
    fake_llm(_question())

    response = _start()

    assert response.items is None
    assert response.options == ["체중 감량", "체력 증진"]


def test_start_returns_session_id_equal_to_proposal_id(fake_llm):
    fake_llm(_question())

    response = _start()

    assert response.session_id == response.proposal_id


def test_decomposition_turn_returns_null_options(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기"))

    response = _start()

    assert response.options is None
    assert [item.title for item in response.items] == ["운동화 꺼내기"]


def test_first_step_field_stays_null_on_decomposition_turn(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기", first_step=_item("현관에 서 있기")))

    response = _start()

    assert response.first_step is None


def test_first_step_becomes_the_head_of_items(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기", first_step=_item("현관에 서 있기")))

    response = _start()

    assert [item.title for item in response.items] == [
        "현관에 서 있기",
        "운동화 꺼내기",
    ]


def test_first_step_duplicated_in_items_is_kept_once(fake_llm):
    fake_llm(_decomposition("현관에 서 있기", first_step=_item("현관에 서 있기")))

    response = _start()

    assert [item.title for item in response.items] == ["현관에 서 있기"]


def test_items_are_capped_at_five(fake_llm):
    fake_llm(_decomposition(*[f"단계 {index}" for index in range(7)]))

    response = _start()

    assert len(response.items) == 5


def test_first_step_takes_a_slot_of_the_item_cap(fake_llm):
    fake_llm(
        _decomposition(
            *[f"단계 {index}" for index in range(5)], first_step=_item("현관에 서 있기")
        )
    )

    response = _start()

    assert [item.title for item in response.items][:2] == ["현관에 서 있기", "단계 0"]
    assert len(response.items) == 5


def test_duplicate_item_titles_are_removed(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기", "운동화 꺼내기 ", "산책하기"))

    response = _start()

    assert [item.title for item in response.items] == ["운동화 꺼내기", "산책하기"]


def test_source_excerpt_is_always_the_target_title(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기"))

    response = _start()

    assert response.items[0].source_excerpt == TARGET_TITLE


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", "\u2028"])
def test_source_excerpt_folds_newlines_in_the_target_title(fake_llm, separator: str):
    fake_llm(_decomposition("운동화 꺼내기"))

    response = _start(title=f"운동{separator}시작하기")

    assert response.items[0].source_excerpt == "운동 시작하기"


def test_decompose_only_fields_are_null(fake_llm):
    fake_llm(_decomposition("운동화 꺼내기"))

    item = _start().items[0]

    assert (item.memo, item.due_date, item.due_time, item.reminder_minutes_before) == (
        None,
        None,
        None,
        None,
    )


def test_out_of_range_importance_becomes_null(fake_llm):
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=False,
            assistant_text="나눴어요.",
            options=[],
            items=[_item("운동화 꺼내기", importance=7)],
            first_step=None,
        )
    )

    assert _start().items[0].importance is None


def test_non_positive_estimated_minutes_becomes_null(fake_llm):
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=False,
            assistant_text="나눴어요.",
            options=[],
            items=[_item("운동화 꺼내기", estimated_minutes=0)],
            first_step=None,
        )
    )

    assert _start().items[0].estimated_minutes is None


def test_empty_items_on_decomposition_turn_is_rejected(fake_llm):
    fake_llm(_decomposition())

    with pytest.raises(InvalidAIResponseError):
        _start()


def test_blank_item_titles_alone_are_rejected(fake_llm):
    fake_llm(_decomposition("   "))

    with pytest.raises(InvalidAIResponseError):
        _start()


def test_duplicate_options_are_removed(fake_llm):
    fake_llm(_question(options=["체력 증진", "체력 증진 ", "체중 감량"]))

    response = _start()

    assert response.options == ["체력 증진", "체중 감량"]


def test_options_are_capped_at_four(fake_llm):
    fake_llm(_question(options=[f"선택지 {index}" for index in range(6)]))

    response = _start()

    assert len(response.options) == 4


def test_question_with_too_few_options_falls_back_to_decomposition(fake_llm):
    # 준비: 질문이라면서 선택지가 하나뿐인 응답에도 items를 함께 담아 보낸다.
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=True,
            assistant_text="목적이 뭔가요?",
            options=["체력 증진"],
            items=[_item("운동화 꺼내기")],
            first_step=None,
        )
    )

    response = _start()

    assert response.items is not None
    assert response.options is None


def test_question_with_blank_text_falls_back_to_decomposition(fake_llm):
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=True,
            assistant_text="   ",
            options=["체중 감량", "체력 증진"],
            items=[_item("운동화 꺼내기")],
            first_step=None,
        )
    )

    response = _start()

    assert response.items is not None


def test_continue_restores_the_previous_conversation(fake_llm):
    calls = fake_llm(_question(), _decomposition("운동화 꺼내기"))
    started = _start()

    _continue(started.session_id)

    conversation = calls[-1]["input_text"]
    assert "[도우미] 운동을 시작하려는 주된 목적이 뭔가요?" in conversation
    assert "[사용자] 체력 증진이 목적이야" in conversation


def test_continue_restores_the_offered_options(fake_llm):
    calls = fake_llm(_question(), _decomposition("운동화 꺼내기"))
    started = _start()

    _continue(started.session_id)

    assert "(선택지: 체중 감량 · 체력 증진)" in calls[-1]["input_text"]


def test_continue_restores_the_last_decomposition(fake_llm):
    calls = fake_llm(_decomposition("운동화 꺼내기", "산책하기"))
    started = _start()

    _continue(started.session_id, "더 잘게 쪼개줘")

    conversation = calls[-1]["input_text"]
    assert "## 직전 분해 결과" in conversation
    assert "1. 운동화 꺼내기" in conversation
    assert "2. 산책하기" in conversation


def test_rebuilt_list_replaces_the_previous_one(fake_llm):
    fake_llm(
        _decomposition("운동화 꺼내기", "산책하기"),
        _decomposition("운동화 찾기", "운동화 신기", "동네 한 바퀴 걷기"),
    )
    started = _start()

    response = _continue(started.session_id, "더 잘게 쪼개줘")

    assert [item.title for item in response.items] == [
        "운동화 찾기",
        "운동화 신기",
        "동네 한 바퀴 걷기",
    ]


def test_rebuilt_list_keeps_the_item_cap(fake_llm):
    fake_llm(
        _decomposition("운동화 꺼내기"),
        _decomposition(*[f"단계 {index}" for index in range(8)]),
    )
    started = _start()

    response = _continue(started.session_id, "더 잘게 쪼개줘")

    assert len(response.items) == 5


def test_instruction_forces_a_decomposition_turn(fake_llm):
    # 준비: 지시가 있는데도 모델이 질문을 반환하는 상황을 만든다.
    fake_llm(
        DecomposeModelOutput(
            needs_clarification=True,
            assistant_text="목적이 뭔가요?",
            options=["체중 감량", "체력 증진"],
            items=[_item("운동화 꺼내기")],
            first_step=None,
        )
    )

    response = _start(instruction="물리적 행동 수준으로 더 잘게")

    assert response.items is not None
    assert response.options is None


def test_instruction_leaves_no_remaining_question_in_the_prompt(fake_llm):
    calls = fake_llm(_decomposition("운동화 꺼내기"))

    _start(instruction="물리적 행동 수준으로 더 잘게")

    assert "남은 질문 횟수: 0회" in calls[-1]["instructions"]


def test_instruction_keeps_forcing_decomposition_on_later_turns(fake_llm):
    forced_question = DecomposeModelOutput(
        needs_clarification=True,
        assistant_text="목적이 뭔가요?",
        options=["체중 감량", "체력 증진"],
        items=[_item("운동화 꺼내기")],
        first_step=None,
    )
    fake_llm(_decomposition("산책하기"), forced_question)
    session_id = _start(instruction="물리적 행동 수준으로 더 잘게").session_id

    response = _continue(session_id, "더 잘게 쪼개줘")

    assert response.items is not None


def test_target_notes_and_instruction_reach_the_prompt(fake_llm):
    calls = fake_llm(_decomposition("운동화 꺼내기"))

    _start(notes="무릎이 안 좋다", instruction="물리적 행동 수준으로 더 잘게")

    conversation = calls[-1]["input_text"]
    assert "메모: 무릎이 안 좋다" in conversation
    assert "지시: 물리적 행동 수준으로 더 잘게" in conversation


def test_question_limit_is_announced_to_the_model(fake_llm):
    calls = fake_llm(_question())
    started = _start()
    session_id = started.session_id

    for _ in range(decompose_service.MAX_QUESTIONS - 1):
        _continue(session_id)

    assert "남은 질문 횟수: 1회" in calls[-1]["instructions"]


def test_turn_after_question_limit_is_forced_to_decompose(fake_llm):
    # 준비: 모델이 상한을 넘겨서도 계속 질문하는 상황을 만든다.
    forced_question = DecomposeModelOutput(
        needs_clarification=True,
        assistant_text="하나만 더 물을게요.",
        options=["체중 감량", "체력 증진"],
        items=[_item("운동화 꺼내기")],
        first_step=None,
    )
    fake_llm(_question(), forced_question)
    session_id = _start().session_id
    for _ in range(decompose_service.MAX_QUESTIONS - 1):
        _continue(session_id)

    response = _continue(session_id)

    assert response.items is not None
    assert response.options is None


def test_question_limit_leaves_no_remaining_question_in_the_prompt(fake_llm):
    calls = fake_llm(
        *[_question()] * decompose_service.MAX_QUESTIONS,
        _decomposition("운동화 꺼내기"),
    )
    session_id = _start().session_id
    for _ in range(decompose_service.MAX_QUESTIONS - 1):
        _continue(session_id)

    _continue(session_id)

    assert "남은 질문 횟수: 0회" in calls[-1]["instructions"]


def test_decomposition_turn_does_not_consume_the_question_limit(fake_llm):
    calls = fake_llm(_decomposition("운동화 꺼내기"))
    session_id = _start().session_id

    _continue(session_id, "더 잘게 쪼개줘")

    assert "남은 질문 횟수: 5회" in calls[-1]["instructions"]


def test_continue_rejects_unknown_session(fake_llm):
    fake_llm(_question())

    with pytest.raises(SessionNotFoundError):
        _continue("발급된-적-없는-세션")


def test_continue_rejects_expired_session(fake_llm, advance: Callable[[float], None]):
    fake_llm(_question())
    started = _start()

    advance(settings.session_ttl_seconds)

    with pytest.raises(SessionNotFoundError):
        _continue(started.session_id)


def test_continue_rejects_session_without_decompose_start(fake_llm):
    fake_llm(_question())
    session = session_service.create_session()

    with pytest.raises(SessionNotFoundError):
        _continue(session.session_id)


def test_failed_turn_does_not_record_the_conversation(fake_llm):
    fake_llm(_question(), AIProviderError("실패"))
    started = _start()

    with pytest.raises(AIProviderError):
        _continue(started.session_id)

    restored = session_service.get_session(started.session_id)
    assert [turn.role for turn in restored.turns] == ["assistant"]


def test_failed_turn_does_not_consume_the_question_limit(fake_llm):
    calls = fake_llm(_question(), AIProviderError("실패"), _question())
    started = _start()
    with pytest.raises(AIProviderError):
        _continue(started.session_id)

    _continue(started.session_id)

    assert "남은 질문 횟수: 4회" in calls[-1]["instructions"]


def test_rate_limit_is_checked_before_the_model_call(
    fake_llm, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    calls = fake_llm(_question())
    _start()

    with pytest.raises(ProtectionLimitError):
        _start()

    assert len(calls) == 1


def test_idempotency_key_reuses_the_started_session(fake_llm):
    calls = fake_llm(_question())
    payload = DecomposeStartRequest(target=DecomposeTarget(title=TARGET_TITLE))

    first = decompose_service.start_decompose(payload, "retry-key")
    second = decompose_service.start_decompose(payload, "retry-key")

    assert first.session_id == second.session_id
    assert len(calls) == 1


def test_requests_without_idempotency_key_start_new_sessions(fake_llm):
    fake_llm(_question())

    first = _start()
    second = _start()

    assert first.session_id != second.session_id


def test_user_input_never_reaches_the_unmasked_instructions(fake_llm):
    # 준비: 마스킹은 llm_service가 input_text에만 적용해, 지시문에 실린 원문은 샌다.
    calls = fake_llm(_decomposition("연락하기"))

    _start(title="치과 예약하기", notes="010-1234-5678로 전화")

    assert "010-1234-5678" in calls[-1]["input_text"]
    assert "010-1234-5678" not in calls[-1]["instructions"]
