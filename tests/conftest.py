"""여러 테스트가 함께 사용하는 fixture.

개발·운영 DB에 연결하지 않고 테스트마다 새 인메모리 SQLite를 만들어 쓴다.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# 엔드포인트에 아직 연결되지 않은 모델도 테이블이 만들어지도록 직접 등록한다.
import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import (
    idempotency_service,
    llm_service,
    rate_limit_service,
    session_service,
)

TEST_DATABASE_URL = "sqlite://"  # 파일을 만들지 않는 인메모리 DB


@pytest.fixture(autouse=True)
def reset_process_state() -> None:
    """프로세스 메모리에 남은 세션·멱등 응답·요청 기록을 테스트마다 비운다."""
    session_service.reset_sessions()
    idempotency_service.reset_idempotency()
    rate_limit_service.reset_rate_limit()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """테스트마다 독립된 인메모리 DB 세션을 제공한다."""
    # StaticPool을 써야 인메모리 DB가 커넥션 하나로 유지된다.
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    """llm_service가 실제 OpenAI 대신 미리 정한 출력이나 예외를 내게 바꾼다."""

    def install(output: object) -> None:
        """다음 LLM 호출이 지정한 출력이나 예외를 내도록 설치한다."""

        # 실제 함수와 같은 시그니처로 선언해 호출부의 인자 드리프트를 잡는다.
        def fake_generate_structured(
            instructions: str, input_text: str, output_type: type
        ) -> object:
            """설치할 때 받은 출력이나 예외로 OpenAI 호출을 대체한다."""
            if isinstance(output, Exception):
                raise output
            assert isinstance(output, output_type)
            return output

        monkeypatch.setattr(
            llm_service, "generate_structured", fake_generate_structured
        )

    return install


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """테스트 DB를 사용하는 애플리케이션 클라이언트를 제공한다."""

    def override_get_db() -> Generator[Session, None, None]:
        """요청에 테스트 DB 세션을 주입한다."""
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
