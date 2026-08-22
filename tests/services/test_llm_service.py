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
        """Responses parse 대역을 노출하는 가짜 OpenAI 클라이언트."""

        def __init__(self, **kwargs: object) -> None:
            """생성 인자를 기록하고 parse 대역을 연결한다."""
            recorded["client"] = kwargs
            self.responses = SimpleNamespace(parse=parse)

    monkeypatch.setattr(llm_service, "OpenAI", _StubClient)
    return recorded


def _generate(input_text: str = "{}") -> object:
    """고정 인자로 generate_structured를 호출한다."""
    return llm_service.generate_structured(
        instructions="지시문", input_text=input_text, output_type=BrainDumpModelOutput
    )


def _completed(title: str) -> BrainDumpCompletedOutput:
    """제목 하나짜리 완료 상태의 모델 출력을 만든다."""
    return BrainDumpCompletedOutput.model_validate(
        {
            "status": "completed",
            "result": {"candidates": [{"title": title, "memo": ""}]},
        }
    )


def _record_parse_kwargs(monkeypatch: pytest.MonkeyPatch, output: object) -> dict:
    """SDK가 받은 인자를 기록하는 클라이언트를 주입한다."""
    parse_kwargs: dict = {}

    def parse(**kwargs: object):
        """SDK 호출 인자를 기록하고 지정한 출력을 감싸 반환한다."""
        parse_kwargs.update(kwargs)
        return SimpleNamespace(output_parsed=SimpleNamespace(response=output))

    _install_client(monkeypatch, parse)
    return parse_kwargs


def test_generate_structured_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "openai_api_key", None)

    with pytest.raises(AINotConfiguredError):
        _generate()


def test_generate_structured_maps_sdk_error(
    configured, monkeypatch: pytest.MonkeyPatch
):
    def parse(**kwargs: object):
        """OpenAI 연결 실패를 재현한다."""
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
        """불완전한 모델 출력을 검증해 오류를 재현한다."""
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
    parse_kwargs = _record_parse_kwargs(monkeypatch, expected)

    # 실행
    _generate()

    # 확인
    assert parse_kwargs["model"] == "gpt-4.1-mini"
    assert parse_kwargs["instructions"] == "지시문"
    assert parse_kwargs["input"] == "{}"
    assert parse_kwargs["max_output_tokens"] == settings.openai_max_output_tokens
    text_format = parse_kwargs["text_format"]
    assert text_format.model_fields["response"].annotation == BrainDumpModelOutput
    # SDK가 schema name으로 보내는 __name__이 OpenAI 제약을 지키는지 확인한다.
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", text_format.__name__)


def test_generate_structured_wires_client_settings(
    configured, monkeypatch: pytest.MonkeyPatch
):
    expected = BrainDumpCompletedOutput.model_validate(
        {"status": "completed", "result": {"candidates": []}}
    )
    client_kwargs = _install_client(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(
            output_parsed=SimpleNamespace(response=expected)
        ),
    )

    _generate()

    assert client_kwargs["client"] == {
        "api_key": "test-key",
        "timeout": settings.openai_timeout_seconds,
    }


def test_generate_structured_masks_personal_data_before_sending(
    configured, monkeypatch: pytest.MonkeyPatch
):
    parse_kwargs = _record_parse_kwargs(monkeypatch, _completed("연락하기"))

    _generate(input_text='{"text": "010-1234-5678로 연락"}')

    assert "010-1234-5678" not in parse_kwargs["input"]
    assert "[전화1]" in parse_kwargs["input"]


def test_generate_structured_restores_personal_data_in_output(
    configured, monkeypatch: pytest.MonkeyPatch
):
    # 준비: 모델이 마스킹 표기를 그대로 실어 응답한 상황이다.
    _record_parse_kwargs(monkeypatch, _completed("[전화1]에게 연락하기"))

    output = _generate(input_text='{"text": "010-1234-5678로 연락"}')

    assert output.result.candidates[0].title == "010-1234-5678에게 연락하기"


def test_generate_structured_log_excludes_input_and_prompt(
    configured, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def parse(**kwargs: object):
        """로그 정책을 확인할 OpenAI 연결 실패를 재현한다."""
        raise openai.APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        )

    _install_client(monkeypatch, parse)

    with pytest.raises(AIProviderError):
        _generate(input_text='{"text": "010-1234-5678로 연락"}')

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "APIConnectionError" in logged
    assert "010-1234-5678" not in logged
    assert "지시문" not in logged
