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
    database_url: str = "sqlite:///./untangle.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 30.0


settings = Settings()
