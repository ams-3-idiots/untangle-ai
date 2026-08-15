"""Swagger 문서 상단에 표시할 앱 설명과 태그 목록."""

API_DESCRIPTION = """
Untangle 생산성 앱의 AI 기능 API입니다.

- 인증이 붙기 전까지 내부 개발 환경에서만 사용합니다.
- `ai-sessions` API는 서버가 세션을 발급하고 대화 상태를 일정 시간 보관합니다.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "서버 상태 확인"},
    {"name": "ai-sessions", "description": "AI 대화 세션 생성과 브레인덤프"},
]
