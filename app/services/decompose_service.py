"""할 일 쪼개기 대화의 복원·턴 전환과 분해 결과 정규화를 담당한다.

앱은 매 턴 이번 발화 하나만 보내므로, 대화 맥락은 TTL 세션에서 복원해 프롬프트로
되살린다.
"""

from pydantic import ValidationError

from app.exceptions.ai import AI_UNAVAILABLE_MESSAGE, InvalidAIResponseError
from app.exceptions.session import SessionNotFoundError
from app.schemas.decompose import (
    MAX_ITEMS,
    MAX_OPTIONS,
    MIN_OPTIONS,
    DecomposeItemModelOutput,
    DecomposeMessageRequest,
    DecomposeModelOutput,
    DecomposeResponse,
    DecomposeStartRequest,
)
from app.schemas.task_draft import TaskDraft, normalize_task_drafts
from app.services import (
    idempotency_service,
    llm_service,
    rate_limit_service,
    session_service,
)
from app.services.session_service import ConversationTurn, DecomposeState, Session

MAX_QUESTIONS = 5
"""대화 전체에서 허용하는 질문 턴 횟수."""

_DECOMPOSE_INSTRUCTIONS = """\
너는 사용자와 대화하며 큰 할 일을 지금 바로 착수할 수 있는 작은 단계로 쪼개는
도우미다. 입력에는 쪼갤 대상과 지금까지의 대화, 직전에 네가 낸 분해 결과가 들어
있다.

분해 전에 아래 5개 항목의 맥락을 대화로 파악한다(내부 가이드 — 사용자에게 나열하지
않는다).
- 왜 하는가 — 목적·동기
- 지금 어디까지 왔나 — 현재 진행 상태
- 무엇이 되면 끝인가 — 완료 기준·원하는 결과물
- 지금 낼 수 있는 여력 — 가용 시간·에너지
- 시작을 막는 것 — 걸림돌·막히는 지점

대화 규칙:
- 한 턴에 질문 하나만 한다(needs_clarification=true). 무엇을 어떤 순서로 물을지는
  자유롭게 정하되, 대상이나 지금까지의 대화로 이미 분명해진 항목은 다시 묻지 않는다.
- 질문에는 고르기 쉬운 선택지 2~4개를 options에 함께 담는다. 이 대상과 앞선 답에
  맞춘 실제 있을 법한 것들로 쓰고 '기타'는 넣지 않는다. 짧고 담백하게 쓴다.
- 사용자가 선택지 밖의 말을 하면 그 맥락을 반영해 다음 질문을 조정한다. 되묻거나
  평가하지 않는다.
- 대상에 지시가 있으면 질문 없이 바로 분해한다.
- "그냥 쪼개줘"·"모르겠어"처럼 진행을 원하는 발화에는 지금까지의 맥락만으로 즉시
  분해한다.

분해 규칙(needs_clarification=false):
- items는 대상을 같은 뎁스에서 대체하는, 실행 순서대로의 전체 목록이다. 하위 작업이
  아니라 대상 자체를 잘게 나눈 것이며, 직전 분해 결과가 있으면 그것을 통째로
  대체한다.
- "더 잘게"는 직전 분해 결과를 기준으로 재구성한다. 이때 원래 목록에 있던 일은
  하나도 빠뜨리지 않는다 — 각 항목을 더 잘게 나누거나, 그대로 둘 항목은 같은 제목으로
  다시 포함시켜 시작부터 끝까지의 흐름을 보존한다.
- 같은 일을 뜻하는 항목을 두 번 넣지 않는다.
- 항목 제목은 구체적이고 바로 할 수 있는 행동을 동사로 끝나는 한 문장으로 짧게 쓴다.
- 각 항목과 first_step에는 importance(1=높음, 2=중간, 3=낮음)와 estimated_minutes를
  반드시 제안한다. 실행 순서상 먼저 하거나 막힌 곳을 뚫는 항목이 1이고, 애매하면 2다.
- first_step은 items와 질적으로 다르다 — 고민이나 준비 없이 5초 안에 몸으로 시작할
  수 있는 가장 작은 물리적 한 동작으로 쓴다. 걸림돌을 들었다면 그것을 우회하는
  행동으로 만든다. items에 이미 있는 단계를 first_step으로 다시 쓰지 않는다.
- first_step을 포함해 모두 합쳐 5개를 넘지 않는다.
- assistant_text는 질문 턴이면 질문 문장 그 자체이고, 분해 턴이면 한두 문장 설명이다.
- 사용자가 쓴 언어로 답한다.
"""


def start_decompose(
    payload: DecomposeStartRequest, idempotency_key: str | None = None
) -> DecomposeResponse:
    """새 세션을 만들고 쪼개기 대화의 첫 턴을 진행한다."""
    return idempotency_service.run_idempotent(
        idempotency_key, lambda: _start_decompose(payload)
    )


def continue_decompose(
    session_id: str,
    payload: DecomposeMessageRequest,
    idempotency_key: str | None = None,
) -> DecomposeResponse:
    """복원한 대화에 이번 발화를 더해 다음 턴을 진행한다."""
    return idempotency_service.run_idempotent(
        idempotency_key, lambda: _continue_decompose(session_id, payload)
    )


def _start_decompose(payload: DecomposeStartRequest) -> DecomposeResponse:
    """대상 스냅샷을 세션에 기록하고 첫 응답을 만든다."""
    rate_limit_service.check_rate_limit()
    session = session_service.create_session()
    session.decompose = DecomposeState(
        target_title=_single_line(payload.target.title),
        target_notes=payload.target.notes or None,
        instruction=payload.instruction or None,
    )
    return _run_turn(session)


def _continue_decompose(
    session_id: str, payload: DecomposeMessageRequest
) -> DecomposeResponse:
    """살아 있는 쪼개기 세션에 이번 발화를 더해 다음 응답을 만든다."""
    session = session_service.get_session(session_id)
    if session.decompose is None:
        # 다른 기능이 만든 세션에 이어가기를 부른 경우로, 없는 세션과 같은 404다.
        raise SessionNotFoundError(f"ai session not found: {session_id}")
    rate_limit_service.check_rate_limit()
    session.turns.append(ConversationTurn(role="user", text=payload.message))
    return _run_turn(session)


def _run_turn(session: Session) -> DecomposeResponse:
    """모델을 호출하고 질문 턴 또는 분해 턴으로 대화를 이어 저장한다."""
    state = session.decompose
    output = llm_service.generate_structured(
        instructions=_with_question_state(state),
        input_text=_conversation_text(session),
        output_type=DecomposeModelOutput,
    )
    assistant_text = output.assistant_text.strip()
    options = _valid_options(output.options)

    if (
        _questionable(state)
        and output.needs_clarification
        and assistant_text
        and len(options) >= MIN_OPTIONS
    ):
        return _finish_question_turn(session, assistant_text, options)
    return _finish_decomposition_turn(session, assistant_text, output)


def _questionable(state: DecomposeState) -> bool:
    """이번 턴에 질문을 돌려줄 수 있는지 판단한다.

    지시가 있거나 질문 한도에 닿았으면 모델이 질문해도 분해 턴을 강제한다.
    """
    return state.instruction is None and state.asked_questions < MAX_QUESTIONS


def _finish_question_turn(
    session: Session, assistant_text: str, options: list[str]
) -> DecomposeResponse:
    """질문 하나를 기록하고 `items`가 null인 응답을 만든다."""
    response = _build_response(
        session_id=session.session_id,
        items=None,
        options=options,
        assistant_text=assistant_text,
    )
    session.decompose.asked_questions += 1
    session.turns.append(
        ConversationTurn(
            role="assistant", text=f"{assistant_text} (선택지: {' · '.join(options)})"
        )
    )
    session_service.save_session(session)
    return response


def _finish_decomposition_turn(
    session: Session, assistant_text: str, output: DecomposeModelOutput
) -> DecomposeResponse:
    """전체 목록을 정규화해 기록하고 `options`가 null인 응답을 만든다."""
    items = _decomposed_items(output, session.decompose.target_title)
    response = _build_response(
        session_id=session.session_id,
        items=items,
        options=None,
        assistant_text=assistant_text,
    )
    session.decompose.last_items = items
    session.turns.append(ConversationTurn(role="assistant", text=assistant_text))
    session_service.save_session(session)
    return response


def _with_question_state(state: DecomposeState) -> str:
    """남은 질문 횟수를 지시문에 덧붙인다."""
    remaining = 0 if state.instruction else MAX_QUESTIONS - state.asked_questions
    lines = [_DECOMPOSE_INSTRUCTIONS, f"남은 질문 횟수: {max(remaining, 0)}회"]
    if remaining <= 0:
        lines.append("남은 질문이 없으므로 이번 턴에는 반드시 분해 결과를 낸다.")
    return "\n".join(lines)


def _conversation_text(session: Session) -> str:
    """대상·직전 분해 결과·대화를 모델이 읽을 하나의 입력으로 만든다."""
    state = session.decompose
    lines = ["## 쪼갤 대상", state.target_title]
    if state.target_notes:
        lines.append(f"메모: {state.target_notes}")
    if state.instruction:
        lines.append(f"지시: {state.instruction}")
    if state.last_items:
        lines.append("")
        lines.append("## 직전 분해 결과")
        lines.extend(
            f"{index}. {item.title}"
            for index, item in enumerate(state.last_items, start=1)
        )
    if session.turns:
        lines.append("")
        lines.append("## 대화")
        lines.extend(f"[{_speaker(turn)}] {turn.text}" for turn in session.turns)
    return "\n".join(lines)


def _speaker(turn: ConversationTurn) -> str:
    """대화 기록에 붙일 화자 이름을 고른다."""
    return "사용자" if turn.role == "user" else "도우미"


def _valid_options(options: list[str]) -> list[str]:
    """빈 값과 중복을 걸러낸 뒤 상한까지만 남긴다."""
    seen: set[str] = set()
    valid: list[str] = []
    for option in options:
        text = option.strip()
        dedupe_key = text.casefold()
        if not text or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        valid.append(text)
        if len(valid) == MAX_OPTIONS:
            break
    return valid


def _decomposed_items(
    output: DecomposeModelOutput, target_title: str
) -> list[TaskDraft]:
    """'지금 할 첫 단계'를 맨 앞에 합친 전체 목록을 정규화한다."""
    raw = [] if output.first_step is None else [output.first_step]
    raw.extend(output.items)
    try:
        items = normalize_task_drafts(
            _draft_source(item, target_title) for item in raw
        )[:MAX_ITEMS]
    except ValidationError as exc:
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE) from exc
    if not items:
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE)
    return items


def _draft_source(
    item: DecomposeItemModelOutput, target_title: str
) -> dict[str, object]:
    """쪼개기에서 항상 null인 필드를 뺀 정규화 입력을 만든다."""
    return {
        "title": item.title,
        "importance": item.importance,
        "estimated_minutes": item.estimated_minutes,
        "source_excerpt": target_title,
    }


def _single_line(title: str) -> str:
    """`sourceExcerpt`로 나갈 대상 제목의 개행을 공백으로 접는다.

    `splitlines`가 CR·CRLF와 유니코드 줄 구분자까지 다뤄 Spring의 `\\R` 치환과 맞는다.
    """
    return " ".join(title.splitlines()).strip()


def _build_response(
    session_id: str,
    items: list[TaskDraft] | None,
    options: list[str] | None,
    assistant_text: str,
) -> DecomposeResponse:
    """모델 출력이 응답 DTO 제약을 어기면 `InvalidAIResponseError`로 바꾼다."""
    try:
        return DecomposeResponse(
            session_id=session_id,
            proposal_id=session_id,
            items=items,
            options=options,
            assistant_text=assistant_text,
        )
    except ValidationError as exc:
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE) from exc
