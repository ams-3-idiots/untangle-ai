"""애플리케이션 설정.

접속 정보나 실행 환경에 따라 달라지는 값은 모두 여기서 읽는다.
다른 레이어는 이 모듈의 `settings`만 참조하고, 환경 변수를 직접 읽지 않는다.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "untangle-ai"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./untangle.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_output_tokens: int = 2048
    session_ttl_seconds: float = 1800.0
    idempotency_ttl_seconds: float = 1800.0
    max_sessions: int = 1000
    max_session_turns: int = 50
    max_session_conversation_chars: int = 50000
    max_idempotency_entries: int = 1000
    rate_limit_requests: int = 60
    rate_limit_window_seconds: float = 60.0


settings = Settings()
