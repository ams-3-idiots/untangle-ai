"""단일 provider(OpenAI)에 대한 얇은 structured output 호출을 제공한다."""

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from app.core.config import settings
from app.exceptions.ai import (
    AINotConfiguredError,
    AIProviderError,
    InvalidAIResponseError,
)

_NOT_CONFIGURED_MESSAGE = "AI 기능이 설정되지 않았습니다. 관리자에게 문의해주세요."
_PROVIDER_ERROR_MESSAGE = "AI 응답을 가져오지 못했습니다. 잠시 후 다시 시도해주세요."
_INVALID_RESPONSE_MESSAGE = "AI 응답을 처리하지 못했습니다. 잠시 후 다시 시도해주세요."


class _StructuredOutput[OutputT](BaseModel):
    """OpenAI structured output은 루트가 객체여야 해서 union 출력을 한 겹 감싼다."""

    response: OutputT


def generate_structured[OutputT](
    instructions: str, input_text: str, output_type: type[OutputT]
) -> OutputT:
    """OpenAI 호출 결과를 모델 출력 DTO로 검증해 반환한다."""
    if not settings.openai_api_key or not settings.openai_model:
        raise AINotConfiguredError(_NOT_CONFIGURED_MESSAGE)

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
            input=input_text,
            text_format=output_format,
        )
    except OpenAIError as exc:
        raise AIProviderError(_PROVIDER_ERROR_MESSAGE) from exc
    except ValueError as exc:
        # pydantic ValidationError와 JSONDecodeError 모두 ValueError를 상속한다.
        raise InvalidAIResponseError(_INVALID_RESPONSE_MESSAGE) from exc

    if result.output_parsed is None:
        raise InvalidAIResponseError(_INVALID_RESPONSE_MESSAGE)
    return result.output_parsed.response
