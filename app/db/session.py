"""엔진·세션 팩토리·요청 단위 세션 주입 의존성.

엔드포인트는 `DbSession` 별칭으로 세션을 받고, `services`는 세션을 인자로만 받는다.
요청 밖(배치·CLI·테스트)에서는 `with SessionLocal() as db:` 로 직접 연다.
"""

from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _engine_options(database_url: str) -> dict[str, Any]:
    """SQLite는 요청과 다른 스레드에서 커넥션을 쓰므로 스레드 검사를 끈다."""
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """요청 단위 DB 세션의 정리와 예외 롤백을 책임진다."""
    db = SessionLocal()

    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
