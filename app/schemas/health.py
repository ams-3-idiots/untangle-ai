"""헬스 체크 응답 형식."""

from typing import Literal

from pydantic import BaseModel


class HealthRead(BaseModel):
    status: Literal["ok"]
