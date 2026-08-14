"""애플리케이션 로그에 사용자 입력·프롬프트·시크릿이 실리지 않는지 검증한다."""

import ast
import logging
from collections.abc import Generator
from pathlib import Path

import pytest

import app.main  # noqa: F401  로깅 설정이 적용된 상태를 만든다
from app.core.logging import PROVIDER_LOGGER_NAMES

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical", "log"}
)

_FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "input_text",
        "instructions",
        "prompt",
        "payload",
        "output_parsed",
        "api_key",
        "openai_api_key",
        "assistant_text",
        "clarifications",
        "turns",
    }
)


@pytest.fixture
def verbose_root() -> Generator[None, None, None]:
    """다른 설정이 루트 로거 레벨을 DEBUG로 낮춘 상황을 만든다."""
    root = logging.getLogger()
    original = root.level
    root.setLevel(logging.DEBUG)

    yield

    root.setLevel(original)


def _log_calls(tree: ast.AST) -> list[ast.Call]:
    """`logger.info(...)`처럼 로거를 호출하는 노드만 고른다."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LOG_METHODS
        and "log" in ast.unparse(node.func.value).lower()
    ]


def _identifiers(node: ast.AST) -> set[str]:
    """노드 안에서 참조하는 이름과 속성 이름을 모은다."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def test_log_statements_reference_no_user_content():
    # 준비: app/ 아래 모든 모듈의 로그 호출을 모은다.
    offenders: list[str] = []

    # 실행
    for path in sorted(APP_ROOT.rglob("*.py")):
        for call in _log_calls(ast.parse(path.read_text(encoding="utf-8"))):
            found = _identifiers(call) & _FORBIDDEN_IDENTIFIERS
            if found:
                offenders.append(f"{path.name}:{call.lineno} {sorted(found)}")

    # 확인
    assert offenders == []


def test_provider_loggers_stay_quiet_when_root_is_verbose(verbose_root: None):
    # provider SDK는 DEBUG에서 요청·응답 본문을 그대로 남긴다.
    for name in PROVIDER_LOGGER_NAMES:
        assert not logging.getLogger(name).isEnabledFor(logging.DEBUG)
