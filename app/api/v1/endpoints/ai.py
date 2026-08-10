"""AI 브레인덤프·할 일 쪼개기 엔드포인트를 제공한다."""

from fastapi import APIRouter

from app.schemas.ai import (
    BrainDumpRequest,
    BrainDumpResponse,
    TaskBreakdownRequest,
    TaskBreakdownResponse,
)
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/brain-dump", response_model=BrainDumpResponse)
def run_brain_dump(payload: BrainDumpRequest) -> BrainDumpResponse:
    """브레인덤프 요청을 서비스에 전달한다."""
    return ai_service.run_brain_dump(payload)


@router.post("/task-breakdown", response_model=TaskBreakdownResponse)
def run_task_breakdown(payload: TaskBreakdownRequest) -> TaskBreakdownResponse:
    """할 일 쪼개기 요청을 서비스에 전달한다."""
    return ai_service.run_task_breakdown(payload)
