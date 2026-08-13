"""서버 로그 출력 설정.

기본 파이썬 설정에서는 루트 로거가 WARNING이고 핸들러도 없어 앱의 INFO 기록이
그대로 버려지므로, 앱 로거의 레벨과 출력 핸들러를 여기서 정한다.
"""

import logging.config
from typing import Any

from app.core.config import settings

APP_LOGGER_NAME = "app"

PROVIDER_LOGGER_NAMES = ("openai", "httpx", "httpcore")
"""LLM provider 호출에 관여하는 라이브러리 로거 이름."""

PROVIDER_LOG_LEVEL = "WARNING"


def _provider_loggers() -> dict[str, Any]:
    """provider 라이브러리 로거의 레벨을 고정하는 선언을 만든다.

    이 라이브러리들은 DEBUG에서 요청·응답 본문을 그대로 남기므로, `LOG_LEVEL`을
    낮춰도 프롬프트와 개인정보가 로그로 새지 않게 레벨을 따로 묶어 둔다.
    """
    return {
        name: {"level": PROVIDER_LOG_LEVEL, "propagate": True}
        for name in PROVIDER_LOGGER_NAMES
    }


def _logging_config(level: str) -> dict[str, Any]:
    """앱 로거를 표준 출력에 연결하는 `dictConfig` 설정을 만든다."""
    return {
        "version": 1,
        # uvicorn이 먼저 구성해 둔 자기 로거들을 끄지 않도록 유지한다.
        "disable_existing_loggers": False,
        "formatters": {
            "app": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "app",
            }
        },
        # 핸들러를 앱 로거가 아닌 루트에만 두고 전파시켜야, 로그를 가로채는
        # 다른 루트 핸들러(테스트의 caplog 등)도 같은 기록을 볼 수 있다.
        "root": {"level": "WARNING", "handlers": ["console"]},
        "loggers": {
            APP_LOGGER_NAME: {"level": level, "propagate": True},
            **_provider_loggers(),
        },
    }


def configure_logging() -> None:
    """앱 로그가 설정된 레벨로 표준 출력에 나가도록 로깅을 구성한다."""
    logging.config.dictConfig(_logging_config(settings.log_level))
