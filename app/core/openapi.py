"""Swagger 문서 상단에 표시할 앱 설명과 태그 목록."""

API_DESCRIPTION = """
Untangle 생산성 앱의 AI 기능 API입니다.

- 인증이 붙기 전까지 내부 개발 환경에서만 사용합니다.
- 서버는 대화 상태를 저장하지 않으며, 앱이 구체화 이력을 함께 보냅니다.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "서버 상태 확인"},
    {"name": "ai", "description": "브레인덤프와 할 일 쪼개기 생성 API"},
]
