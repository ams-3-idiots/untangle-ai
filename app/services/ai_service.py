"""브레인덤프·할 일 쪼개기의 질문 이력 규칙과 결과 정규화를 담당한다."""

from pydantic import BaseModel, ValidationError

from app.exceptions.ai import (
    InvalidAIResponseError,
    InvalidClarificationStateError,
)
from app.schemas.ai import (
    MAX_RESULT_ITEMS,
    BrainDumpClarificationOutput,
    BrainDumpClarificationResponse,
    BrainDumpCompletedResponse,
    BrainDumpModelOutput,
    BrainDumpRequest,
    BrainDumpResponse,
    CandidateModelOutput,
    ClarificationAnswer,
    QuestionModelOutput,
    TaskBreakdownClarificationOutput,
    TaskBreakdownClarificationResponse,
    TaskBreakdownCompletedResponse,
    TaskBreakdownModelOutput,
    TaskBreakdownRequest,
    TaskBreakdownResponse,
    TaskBreakdownResultModelOutput,
)
from app.services import llm_service

BRAIN_DUMP_MAX_QUESTIONS = 1
TASK_BREAKDOWN_MAX_QUESTIONS = 3

_INVALID_MODEL_RESPONSE_MESSAGE = (
    "AI가 형식에 맞지 않는 응답을 반환했습니다. 잠시 후 다시 시도해주세요."
)
_REASKED_QUESTION_MESSAGE = (
    "AI가 이미 처리한 질문을 다시 반환했습니다. 잠시 후 다시 시도해주세요."
)
_QUESTION_LIMIT_MESSAGE = (
    "AI가 질문 한도를 넘겨 질문을 반환했습니다. 잠시 후 다시 시도해주세요."
)
_MISSING_FIRST_STEP_MESSAGE = (
    "AI가 first_step 없이 단계를 반환했습니다. 잠시 후 다시 시도해주세요."
)

_BRAIN_DUMP_INSTRUCTIONS = """\
너는 생산성 앱의 브레인덤프 도우미다. 사용자가 쏟아낸 생각(text)에서 바로
실행할 수 있는 할 일 후보를 뽑는다. 입력 JSON에는 원본 text와, 이전 질문에
대한 답변·건너뛰기 이력(clarifications)이 들어 있다.

규칙:
- text와 답변에 근거가 있는 할 일만 후보로 만든다. 근거 있는 후보가 하나라도
  있으면 질문하지 말고 completed로 응답한다.
- 후보가 하나도 없고 해결되지 않은 고민이 드러나면, 직접 해야 하는 일 하나를
  묻는 질문(key="action_detail")을 needs_clarification으로 반환한다.
- 이미 질문에 답했거나 건너뛰었다면 다시 묻지 말고 현재 정보로 completed를
  만든다.
- 감정·상태·바람을 새로운 행동으로 바꾸지 않는다.
- text에 명시된 큰 목표를 임의로 쪼개지 않는다.
- 후보는 최대 5개다. title은 100자 이하의 할 일 한 줄이고, memo는 200자
  이하의 보조 정보이며 없으면 빈 문자열 ""을 쓴다.
- 질문 text는 한 번에 하나만, 200자 이하로 묻는다. options는 아예 없거나
  2~4개이며 각 항목은 50자 이하다.
- 만들 후보가 없고 물을 것도 없으면 빈 candidates로 completed를 반환한다.
- 사용자가 쓴 언어로 답한다.
"""

_TASK_BREAKDOWN_INSTRUCTIONS = """\
너는 생산성 앱의 할 일 쪼개기 도우미다. 목표(goal) 한 줄을 바로 착수할 수
있는 작은 실행 단계로 분해한다. 입력 JSON에는 goal과, 이전 질문에 대한
답변·건너뛰기 이력(clarifications)이 들어 있다.

질문 규칙:
- 정보가 부족할 때만 progress(진행 상태), done(완료 기준), capacity(쓸 수
  있는 시간), blocker(막히는 지점) 중 결과를 가장 크게 바꿀 질문 하나를
  needs_clarification으로 반환한다.
- goal이나 이전 답변에 이미 있는 내용은 다시 묻지 않는다.
- 이미 답했거나 건너뛴 key는 다시 묻지 않는다.
- 모든 항목을 채우는 설문을 하지 않는다. 정보가 충분하면 바로 completed를
  만든다.
- 질문 text는 한 번에 하나만, 200자 이하로 묻는다. options는 아예 없거나
  2~4개이며 각 항목은 50자 이하다.

분해 규칙:
- first_step은 goal에 특화되고 몇 분 안에 바로 시작할 수 있는 가장 작은
  행동이다.
- steps는 first_step 다음에 실행할 순서대로 나열한다.
- first_step과 steps를 합쳐 최대 5개다. title은 100자 이하의 할 일 한
  줄이고, memo는 200자 이하의 보조 정보이며 없으면 빈 문자열 ""을 쓴다.
- 단계를 만들 수 없으면 first_step=null, steps=[]로 응답한다.
- steps가 있으면 first_step이 반드시 있어야 한다.
- 사용자가 쓴 언어로 답한다.
"""


def run_brain_dump(payload: BrainDumpRequest) -> BrainDumpResponse:
    """브레인덤프 입력에서 구체화 질문 하나 또는 할 일 후보를 만든다."""
    _check_clarification_state(payload.clarifications, BRAIN_DUMP_MAX_QUESTIONS)
    output = llm_service.generate_structured(
        instructions=_with_question_state(
            _BRAIN_DUMP_INSTRUCTIONS,
            payload.clarifications,
            BRAIN_DUMP_MAX_QUESTIONS,
        ),
        input_text=payload.model_dump_json(),
        output_type=BrainDumpModelOutput,
    )
    if isinstance(output, BrainDumpClarificationOutput):
        _check_model_question(
            output.question, payload.clarifications, BRAIN_DUMP_MAX_QUESTIONS
        )
        return _build_response(
            BrainDumpClarificationResponse, question=output.question.model_dump()
        )
    candidates = _normalize_candidates(output.result.candidates)
    return _build_response(
        BrainDumpCompletedResponse, result={"candidates": candidates}
    )


def run_task_breakdown(payload: TaskBreakdownRequest) -> TaskBreakdownResponse:
    """목표 한 줄에서 구체화 질문 하나 또는 실행 단계를 만든다."""
    _check_clarification_state(payload.clarifications, TASK_BREAKDOWN_MAX_QUESTIONS)
    output = llm_service.generate_structured(
        instructions=_with_question_state(
            _TASK_BREAKDOWN_INSTRUCTIONS,
            payload.clarifications,
            TASK_BREAKDOWN_MAX_QUESTIONS,
        ),
        input_text=payload.model_dump_json(),
        output_type=TaskBreakdownModelOutput,
    )
    if isinstance(output, TaskBreakdownClarificationOutput):
        _check_model_question(
            output.question, payload.clarifications, TASK_BREAKDOWN_MAX_QUESTIONS
        )
        return _build_response(
            TaskBreakdownClarificationResponse, question=output.question.model_dump()
        )
    return _build_response(
        TaskBreakdownCompletedResponse, result=_normalize_breakdown(output.result)
    )


def _check_clarification_state(
    clarifications: list[ClarificationAnswer], max_questions: int
) -> None:
    """schema가 다루지 않는 업무 규칙인 중복 key와 질문 한도를 검증한다."""
    keys = [item.key for item in clarifications]
    if len(keys) != len(set(keys)):
        raise InvalidClarificationStateError(
            "같은 key의 구체화 답변이 두 번 이상 들어 있습니다."
        )
    if len(keys) > max_questions:
        raise InvalidClarificationStateError(
            f"구체화 답변은 최대 {max_questions}개까지 보낼 수 있습니다."
        )


def _with_question_state(
    instructions: str,
    clarifications: list[ClarificationAnswer],
    max_questions: int,
) -> str:
    """이미 물은 key와 남은 질문 횟수를 지시문에 덧붙인다."""
    asked = ", ".join(item.key for item in clarifications) or "없음"
    remaining = max_questions - len(clarifications)
    lines = [
        instructions,
        f"이미 질문한 key: {asked}",
        f"남은 질문 횟수: {remaining}회",
    ]
    if remaining <= 0:
        lines.append("남은 질문이 없으므로 반드시 completed로 응답한다.")
    return "\n".join(lines)


def _check_model_question(
    question: QuestionModelOutput,
    clarifications: list[ClarificationAnswer],
    max_questions: int,
) -> None:
    """질문 한도와 이미 처리한 key를 어긴 모델 질문을 거른다."""
    if len(clarifications) >= max_questions:
        raise InvalidAIResponseError(_QUESTION_LIMIT_MESSAGE)
    if any(item.key == question.key for item in clarifications):
        raise InvalidAIResponseError(_REASKED_QUESTION_MESSAGE)


def _normalize_candidates(
    candidates: list[CandidateModelOutput],
) -> list[dict[str, str]]:
    """제목을 trim하고 casefold 중복을 제거한 뒤 상한까지만 남긴다."""
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for candidate in candidates:
        title = candidate.title.strip()
        dedupe_key = title.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append({"title": title, "memo": candidate.memo.strip()})
        if len(normalized) == MAX_RESULT_ITEMS:
            break
    return normalized


def _normalize_breakdown(
    result: TaskBreakdownResultModelOutput,
) -> dict[str, object]:
    """first_step을 우선 유지하며 중복 단계를 제거하고 합계 상한을 지킨다."""
    if result.first_step is None:
        if result.steps:
            raise InvalidAIResponseError(_MISSING_FIRST_STEP_MESSAGE)
        return {"first_step": None, "steps": []}
    first_title = result.first_step.title.strip()
    seen = {first_title.casefold()}
    steps: list[dict[str, str]] = []
    for step in result.steps:
        title = step.title.strip()
        dedupe_key = title.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        steps.append({"title": title, "memo": step.memo.strip()})
        if 1 + len(steps) == MAX_RESULT_ITEMS:
            break
    return {
        "first_step": {"title": first_title, "memo": result.first_step.memo.strip()},
        "steps": steps,
    }


def _build_response[ResponseT: BaseModel](
    response_type: type[ResponseT], **fields: object
) -> ResponseT:
    """모델 출력이 응답 DTO 제약을 어기면 `InvalidAIResponseError`로 바꾼다."""
    try:
        return response_type(**fields)
    except ValidationError as exc:
        raise InvalidAIResponseError(_INVALID_MODEL_RESPONSE_MESSAGE) from exc
