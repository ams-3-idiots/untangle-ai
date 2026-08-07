"""모든 모델이 상속하는 선언적 베이스.

`models`가 이 모듈을 참조한다. 반대로 `db`가 `models`를 참조하면 의존 방향이
어긋나므로, 이 파일에서 모델을 import 하지 않는다.
모든 테이블이 등록된 메타데이터가 필요하면 `app.models`를 import 한 뒤
`Base.metadata`를 쓴다.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
