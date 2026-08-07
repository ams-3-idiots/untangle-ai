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

TEST_DATABASE_URL = "sqlite://"  # 파일을 만들지 않는 인메모리 DB


@pytest.fixture
def db() -> Generator[Session, None, None]:
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
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
