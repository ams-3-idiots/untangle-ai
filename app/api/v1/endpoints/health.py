"""헬스 체크 엔드포인트."""

from fastapi import APIRouter

from app.schemas.health import HealthRead
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthRead, summary="서버 상태를 확인한다")
def check_health() -> HealthRead:  # 동기 세션을 쓰므로 def
    """서버가 요청을 처리할 수 있으면 `{"status": "ok"}`를 반환한다."""
    return health_service.check_health()
