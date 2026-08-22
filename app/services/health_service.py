"""헬스 체크 유스케이스.

로직이 거의 없어도 엔드포인트가 서비스를 건너뛰지 않도록 레이어를 유지한다.
"""

from app.schemas.health import HealthRead


def check_health() -> HealthRead:
    """서버가 요청을 처리할 수 있음을 나타내는 상태를 반환한다."""
    return HealthRead(status="ok")
