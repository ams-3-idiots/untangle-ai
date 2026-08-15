"""AI 세션 생성과 브레인덤프의 유스케이스.

세션 보관과 LLM 호출은 다른 서비스에 맡기고, 여기서는 덤프 결과의 정규화·중복
제거와 세션 수명을 갱신하는 시점을 정한다.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from app.exceptions.ai import AI_UNAVAILABLE_MESSAGE, InvalidAIResponseError
from app.schemas.ai_session import (
    MAX_DUMP_TASKS,
    DumpModelOutput,
    DumpRequest,
    DumpResponse,
    DumpTaskModelOutput,
    SessionCreatedResponse,
)
from app.schemas.task_draft import TaskDraft, normalize_task_drafts
from app.services import (
    idempotency_service,
    llm_service,
    rate_limit_service,
    session_service,
)

_DUMP_INSTRUCTIONS = """\
너는 생산성 앱의 브레인덤프 도우미다. 사용자가 쏟아낸 생각(text)에서 바로
실행할 수 있는 할 일 후보를 뽑는다. 입력 JSON에는 원문 text, 앱에 이미 있는 할
일 제목(existing_task_titles), 앱의 현재 시각(client_now)이 들어 있다.

할 일 규칙:
- text에 근거가 있는 할 일만 만든다. 감정·상태·바람을 새로운 행동으로 바꾸지
  않는다.
- text에 명시된 큰 목표를 임의로 쪼개지 않는다.
- existing_task_titles에 이미 있는 할 일은 다시 만들지 않는다.
- tasks는 최대 5개이며, 만들 후보가 없으면 빈 배열로 답한다.

필드 규칙:
- title은 할 일 한 줄이며 비워 두지 않는다.
- 단서가 없는 필드는 빈 문자열이 아니라 null로 둔다.
- importance는 1(높음)·2(중간)·3(낮음) 중 하나다.
- estimated_minutes는 0보다 큰 정수(분)다.
- due_date는 `yyyy-MM-dd`, due_time은 24시간제 `HH:mm` 형식이다. "다음 주"처럼
  상대적인 기한은 client_now를 기준으로 환산하고, client_now가 없으면 null로
  둔다.
- reminder_minutes_before는 10·30·60·180·1440 중 하나다.
- source_excerpt는 근거가 된 text의 일부를 그대로 옮긴 문자열이다. 요약하거나
  고쳐 쓰면 서버가 버린다. 옮길 부분이 없으면 null로 둔다.

assistant_text 규칙:
- 결과를 짧게 설명하는 한두 문장이다.
- tasks가 비면 어떤 내용을 더 적으면 좋을지 안내한다.
- 사용자가 쓴 언어로 답한다.
"""


def create_session() -> SessionCreatedResponse:
    """새 대화 세션을 만들어 앱이 이어서 쓸 세션 식별자를 반환한다."""
    session = session_service.create_session()
    return SessionCreatedResponse(session_id=session.session_id)


def run_dump(
    session_id: str, payload: DumpRequest, idempotency_key: str | None = None
) -> DumpResponse:
    """살아 있는 세션에서 덤프를 실행하고 같은 키의 재시도에는 같은 응답을 준다."""
    session = session_service.get_session(session_id)
    response = idempotency_service.run_idempotent(
        idempotency_key, lambda: _dump(session.session_id, payload)
    )
    # 캐시에서 재사용한 응답도 세션을 쓴 성공 요청이므로 수명을 함께 늘린다.
    session_service.save_session(session)
    return response


def _dump(session_id: str, payload: DumpRequest) -> DumpResponse:
    """마스킹 경계를 거쳐 LLM을 호출하고 정리한 응답을 만든다."""
    rate_limit_service.check_rate_limit()
    output = llm_service.generate_structured(
        instructions=_DUMP_INSTRUCTIONS,
        input_text=payload.model_dump_json(),
        output_type=DumpModelOutput,
    )
    return _build_response(session_id, payload, output)


def _build_response(
    session_id: str, payload: DumpRequest, output: DumpModelOutput
) -> DumpResponse:
    """모델 출력을 정규화해 응답을 만들고, 쓸 수 없는 응답은 `503`으로 바꾼다."""
    try:
        tasks = _normalized_tasks(output.tasks, payload)
        assistant_text = output.assistant_text.strip()
        if not tasks and not assistant_text:
            raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE)
        return DumpResponse(
            proposal_id=session_id, tasks=tasks, assistant_text=assistant_text
        )
    except ValidationError as exc:
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE) from exc


def _normalized_tasks(
    tasks: Iterable[DumpTaskModelOutput], payload: DumpRequest
) -> list[TaskDraft]:
    """근거 없는 발췌를 지우고 이미 있는 할 일을 뺀 뒤 상한까지만 남긴다."""
    existing = {title.strip().lower() for title in payload.existing_task_titles}
    drafts = normalize_task_drafts(_task_fields(task, payload.text) for task in tasks)
    kept = [draft for draft in drafts if draft.title.lower() not in existing]
    return kept[:MAX_DUMP_TASKS]


def _task_fields(task: DumpTaskModelOutput, text: str) -> dict[str, Any]:
    """공통 정규화에 넘길 필드 묶음을 만들면서 발췌의 출처를 확인한다."""
    fields = task.model_dump()
    fields["source_excerpt"] = _verified_excerpt(task.source_excerpt, text)
    return fields


def _verified_excerpt(excerpt: str | None, text: str) -> str | None:
    """입력 원문에 그대로 없는 발췌는 지어낸 근거로 보고 단서 없음(null)으로 바꾼다."""
    trimmed = (excerpt or "").strip()
    if not trimmed or trimmed not in text:
        return None
    return trimmed
