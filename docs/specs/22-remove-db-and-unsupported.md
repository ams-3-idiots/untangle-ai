# DB 골격과 미지원 AI 기능 정리

> 관련 GitHub Issue: [#22](https://github.com/ams-3-idiots/untangle-ai/issues/22)

구현 전 초안이다. 구현 과정에서 확정한 내용을 이 문서에 반영한다.

## 1. 핵심 결정

- 지원 4개 경로 외에는 어떤 경로도 노출하지 않는다. `single-add`, `suggest`,
  기존 `/api/v1/ai/**`는 `404`가 된다.
- 계약 밖 경로의 `404` 본문 형식은 보장하지 않는다.
- `report`는 AI 서버 범위 밖이다 — 기존 Spring 서버에 남는다.
- SQLAlchemy·SQLite·`DATABASE_URL` 설정과 DB 골격을 제거한다.
- AI 서버에는 사용자 계정, 소셜 로그인, JWT 검증이 존재하지 않는다.

## 2. 상세 설계

### 2.1 현행 FastAPI 계약과의 차이

현행 FastAPI 서버는 아래 항목이 모두 다르며, 새 지원 계약으로 대체된다.
기존 경로·DTO·오류 형식은 이 작업에서 제거한다.

| 항목 | 현행 FastAPI | 지원 계약 |
| --- | --- | --- |
| 경로 | `POST /api/v1/ai/brain-dump`, `POST /api/v1/ai/task-breakdown` | `/api/v1/ai-sessions/**` 4개 경로 |
| 대화 상태 | 무상태 — 앱이 `clarifications` 이력을 누적 재전송 | 서버가 TTL 세션에 보관 — 앱은 이번 발화만 전송 |
| 와이어 표기 | snake_case (`first_step`) | camelCase (`firstStep`) |
| 응답 구분 | `status` discriminator (`needs_clarification`/`completed`) | `items`의 null 여부로 턴 구분 |
| 결과 DTO | `{title, memo}` 2필드, `memo` 기본 `""` | `TaskDraft` 8필드, 없는 값은 null |
| 오류 본문 | `{"code", "message"}` | RFC 9457 ProblemDetail |
| 오류 상태 | `400`(규칙 위반), `502`(provider·모델 응답), `503`(설정 누락) | `404`/`422`/`429`/`503` — `400`·`502` 미사용 |
| 검증 실패 본문 | FastAPI 기본 `{"detail": [...]}` | ProblemDetail로 변환 |
| 헤더 | 없음 | `Authorization` 허용·무시, `Idempotency-Key`, `X-Request-Id` |
| 질문 상한 | 브레인덤프 1회, 쪼개기 3회 | 브레인덤프는 질문 없음, 쪼개기 최대 5회 |

### 2.2 제거 대상

- `app/db/`, `app/models/`, `app/repositories/`의 미사용 골격과 SQLAlchemy
  의존성, SQLite·`DATABASE_URL` 설정
- DB 세션을 만드는 테스트 fixture와 DB 실행 안내 문서
- 기존 `/api/v1/ai/brain-dump`, `/api/v1/ai/task-breakdown` endpoint와
  `{"code", "message"}` 오류 계약
- 사용자 계정·소셜 로그인·JWT 검증 관련 코드·설정이 없음을 확인

### 2.3 호환성 테스트 사례

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | `single-add`·`suggest`·기존 `/api/v1/ai/brain-dump`·`/api/v1/ai/task-breakdown` 호출 | `404` — 지원 4경로 외에는 노출되지 않는다 |
| T-02 | 애플리케이션과 전체 테스트 실행 | SQLAlchemy·SQLite·`DATABASE_URL` 없이 동작 |
