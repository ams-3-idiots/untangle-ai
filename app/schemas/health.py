"""헬스 체크 응답 형식."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthRead(BaseModel):
    """헬스 체크 응답."""

    status: Literal["ok"] = Field(description="서버가 정상이면 항상 `ok`")
