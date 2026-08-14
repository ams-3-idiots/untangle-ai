"""단일 provider(OpenAI)에 대한 structured output 호출 경계.

LLM으로 나가는 입력의 개인정보를 가리고, 모델 응답의 문자열을 원문으로 되돌린
검증된 DTO만 돌려준다. provider SDK 객체와 모델 원문은 밖으로 내보내지 않는다.
"""

import logging

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from app.core.config import settings
from app.exceptions.ai import (
    AI_UNAVAILABLE_MESSAGE,
    AINotConfiguredError,
    AIProviderError,
    InvalidAIResponseError,
)
from app.services import masking_service
from app.services.masking_service import MaskingContext

logger = logging.getLogger("app.llm")


class _StructuredOutput[OutputT](BaseModel):
    """OpenAI structured output은 루트가 객체여야 해서 union 출력을 한 겹 감싼다."""

    response: OutputT


def generate_structured[OutputT](
    instructions: str, input_text: str, output_type: type[OutputT]
) -> OutputT:
    """마스킹한 입력으로 OpenAI를 호출하고 원문을 복원한 출력 DTO를 반환한다."""
    if not settings.openai_api_key or not settings.openai_model:
        logger.error("llm call rejected: provider not configured")
        raise AINotConfiguredError(AI_UNAVAILABLE_MESSAGE)

    context = masking_service.new_context()
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    # SDK가 __name__을 schema name으로 그대로 보내는데, 파라미터화된 generic의
    # 이름은 OpenAI의 name 제약([A-Za-z0-9_-], 64자)을 어겨 400이 나므로 바꿔 둔다.
    output_format = _StructuredOutput[output_type]
    output_format.__name__ = "structured_output"
    try:
        result = client.responses.parse(
            model=settings.openai_model,
            instructions=instructions,
            input=context.mask(input_text),
            text_format=output_format,
            max_output_tokens=settings.openai_max_output_tokens,
        )
    except OpenAIError as exc:
        logger.warning("llm call failed: %s", type(exc).__name__)
        raise AIProviderError(AI_UNAVAILABLE_MESSAGE) from exc
    except ValueError as exc:
        # pydantic ValidationError와 JSONDecodeError 모두 ValueError를 상속한다.
        logger.warning("llm response rejected: %s", type(exc).__name__)
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE) from exc

    if result.output_parsed is None:
        logger.warning("llm response rejected: no parsed output")
        raise InvalidAIResponseError(AI_UNAVAILABLE_MESSAGE)

    output = result.output_parsed.response
    if isinstance(output, BaseModel):
        _restore(output, context)
    return output


def _restore(model: BaseModel, context: MaskingContext) -> None:
    """모델 출력에 담긴 모든 문자열의 마스킹 표기를 원문으로 되돌린다."""
    for name in type(model).model_fields:
        setattr(model, name, _restored(getattr(model, name), context))


def _restored(value: object, context: MaskingContext) -> object:
    """문자열은 되돌리고 중첩된 모델과 목록은 따라 들어간다."""
    if isinstance(value, BaseModel):
        _restore(value, context)
        return value
    if isinstance(value, list):
        return [_restored(item, context) for item in value]
    if isinstance(value, str):
        return context.unmask(value)
    return value
