"""모든 모델이 상속하는 선언적 베이스.

`db`는 `models`를 참조하지 않으며, 전체 메타데이터가 필요할 때만 호출부에서
`app.models`를 먼저 불러온다.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """애플리케이션 모델이 공유하는 SQLAlchemy 선언적 베이스."""

    pass
