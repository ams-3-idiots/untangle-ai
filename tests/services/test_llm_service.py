"""OpenAI 호출 함수의 설정 검사와 도메인 오류 변환을 검증한다."""

import re
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.core.config import settings
from app.exceptions.ai import (
    AINotConfiguredError,
    AIProviderError,
    InvalidAIResponseError,
)
from app.schemas.ai import BrainDumpCompletedOutput, BrainDumpModelOutput
from app.services import llm_service


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI 설정이 채워진 상태를 만든다."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_model", "gpt-4.1-mini")


def _install_client(monkeypatch: pytest.MonkeyPatch, parse) -> dict:
    """가짜 OpenAI 클라이언트를 주입하고 클라이언트 생성 인자를 기록한다."""
    recorded: dict = {}

    class _StubClient:
        def __init__(self, **kwargs: object) -> None:
            recorded["client"] = kwargs
            self.responses = SimpleNamespace(parse=parse)

    monkeypatch.setattr(llm_service, "OpenAI", _StubClient)
    return recorded


def _generate() -> object:
    """고정 인자로 generate_structured를 호출한다."""
    return llm_service.generate_structured(
        instructions="지시문", input_text="{}", output_type=BrainDumpModelOutput
    )


def test_generate_structured_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "openai_api_key", None)

    with pytest.raises(AINotConfiguredError):
        _generate()


def test_generate_structured_maps_sdk_error(
    configured, monkeypatch: pytest.MonkeyPatch
):
    def parse(**kwargs: object):
        raise openai.APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        )

    _install_client(monkeypatch, parse)

    with pytest.raises(AIProviderError):
        _generate()


def test_generate_structured_maps_validation_error(
    configured, monkeypatch: pytest.MonkeyPatch
):
    def parse(**kwargs: object):
        # status만 있는 불완전한 응답으로 pydantic 검증 오류를 일으킨다.
        BrainDumpCompletedOutput.model_validate({"status": "completed"})

    _install_client(monkeypatch, parse)

    with pytest.raises(InvalidAIResponseError):
        _generate()


def test_generate_structured_rejects_unparsed_output(
    configured, monkeypatch: pytest.MonkeyPatch
):
    _install_client(monkeypatch, lambda **kwargs: SimpleNamespace(output_parsed=None))

    with pytest.raises(InvalidAIResponseError):
        _generate()


def test_generate_structured_returns_parsed_response(
    configured, monkeypatch: pytest.MonkeyPatch
):
    expected = BrainDumpCompletedOutput.model_validate(
        {"status": "completed", "result": {"candidates": []}}
    )
    _install_client(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(
            output_parsed=SimpleNamespace(response=expected)
        ),
    )

    assert _generate() is expected


def test_generate_structured_wires_settings_and_prompt(
    configured, monkeypatch: pytest.MonkeyPatch
):
    # 준비: 스텁이 받은 인자를 기록해 설정·프롬프트의 SDK 배선을 확인한다.
    expected = BrainDumpCompletedOutput.model_validate(
        {"status": "completed", "result": {"candidates": []}}
    )
    parse_kwargs: dict = {}

    def parse(**kwargs: object):
        parse_kwargs.update(kwargs)
        return SimpleNamespace(output_parsed=SimpleNamespace(response=expected))

    client_kwargs = _install_client(monkeypatch, parse)

    # 실행
    _generate()

    # 확인
    assert client_kwargs["client"] == {
        "api_key": "test-key",
        "timeout": settings.openai_timeout_seconds,
    }
    assert parse_kwargs["model"] == "gpt-4.1-mini"
    assert parse_kwargs["instructions"] == "지시문"
    assert parse_kwargs["input"] == "{}"
    text_format = parse_kwargs["text_format"]
    assert text_format.model_fields["response"].annotation == BrainDumpModelOutput
    # SDK가 schema name으로 보내는 __name__이 OpenAI 제약을 지키는지 확인한다.
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", text_format.__name__)
