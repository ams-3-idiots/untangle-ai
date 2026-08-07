"""헬스 체크 엔드포인트."""

from fastapi import APIRouter

from app.schemas.health import HealthRead
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthRead)
def check_health() -> HealthRead:  # 동기 세션을 쓰므로 def
    return health_service.check_health()
