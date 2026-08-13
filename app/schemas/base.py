"""요청·응답 DTO가 공유하는 와이어 이름 규칙 베이스."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Spring과 동일한 camelCase 와이어 필드 이름을 쓰는 DTO 베이스."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
