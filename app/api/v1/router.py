"""v1 라우터 등록.

새 엔드포인트 모듈을 만들면 여기에 `include_router`로 추가한다.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import ai, health

api_router = APIRouter()
api_router.include_router(ai.router)
api_router.include_router(health.router)
