# Spring과 호환되는 공통 HTTP 계약을 정의한다

API 전체가 공유하는 HTTP 기반 계약 — 경로, 공통 스키마, 헤더, 오류
응답을 확정한다.

## 1. 핵심 결정

- 요청·응답 DTO의 와이어 필드 이름은 Spring과 동일한 camelCase를 유지한다.
  와이어 필드 이름은 HTTP 요청·응답 JSON에 실제로 실리는 키 이름을 말한다.
- 모든 오류 응답 본문은 RFC 9457 ProblemDetail로 통일한다.
- FastAPI 기본 `422` 본문(`{"detail": [...]}`) 대신 ProblemDetail로 변환한다.
- 도메인 오류는 `404`·`429`·`503`에 매핑한다. `400`·`502`는 지원 경로 계약에서
  쓰지 않는다.
- `Authorization` 헤더는 허용하되 검증·사용자 식별에 쓰지 않는다.
- 모든 응답에 `X-Request-Id`를 실어 요청을 추적할 수 있게 한다.

## 2. 상세 설계

### 2.1 공통 헤더 규칙

#### Authorization

- 헤더가 있어도, 없어도, 값이 무엇이어도 요청 처리 결과가 달라지지 않는다.
- JWT 검증·사용자 식별에 사용하지 않으며 로그에도 남기지 않는다.

#### X-Request-Id

서버 로그에서 특정 요청을 추적하는 식별자다. 앱이 버그 리포트·문의에 응답
헤더의 이 값을 첨부하면 해당 요청의 서버 로그를 바로 찾을 수 있다.

- 요청 헤더 값이 `[A-Za-z0-9._-]{1,64}` 패턴에 맞으면 그대로 사용하고, 없거나
  패턴을 벗어나면 서버가 UUID를 생성한다.
- 결정된 값은 모든 응답(오류 포함)의 `X-Request-Id` 헤더에 싣고, 서버 로그의
  요청 추적 식별자로 쓴다.

### 2.2 공통 오류 계약

```json
{ "type": "about:blank", "title": "Not found", "status": 404, "detail": "ai session not found: cace6837-…" }
```

| status | title | 언제 | detail |
| --- | --- | --- | --- |
| `404` | `Not found` | 없는 세션, TTL 만료, 재시작으로 소실, UUID 형식이 아닌 `sessionId`, 쪼개기 시작 기록이 없는 세션에 이어가기 호출 | 세션 식별자를 포함할 수 있음 |
| `422` | `Validation failed` | 요청 본문의 타입·필수값·길이 검증 실패 | `"필드경로: 사유"`를 `"; "`로 연결한 문자열 (필드 경로는 요청 본문 기준, 예: `"text: must not be blank"`) |
| `429` | `Too many requests` | 보호 한도 초과 | 사유 요약 |
| `503` | `AI service unavailable` | provider 설정 누락, timeout·네트워크·호출 실패, 스키마를 벗어난 모델 응답, 사용 가능한 결과가 없는 모델 응답 | 재시도 안내 문구 (고정) |

- `type`은 항상 `"about:blank"`이다. `status`는 HTTP 상태 코드와 같은 값이다.
- `title`은 위 표의 고정 문자열을 유지한다.
- `detail`에 사용자 입력·대화·프롬프트·모델 원문·스택 트레이스를 넣지 않는다.

### 2.3 TaskDraft 공통 규칙

정확한 필드와 타입은 OpenAPI를 따른다. 덤프의 `tasks[]`와 쪼개기의 `items[]`가
공유하는 선택 필드는 값이 없어도 키를 생략하지 않고 `null`로 직렬화한다.

서버는 모델 출력을 그대로 내보내지 않고 다음 정규화를 거친다.

- 제목이 공백뿐인 항목은 버린다.
- 제목의 `strip + 소문자` 결과가 같으면 첫 항목만 남긴다(순서 유지).
- `importance`가 1~3 밖이면 null, `reminderMinutesBefore`가 허용값 밖이면 null로 바꾼다.
- `estimatedMinutes`는 소수점을 버려 정수로 만든 뒤, 0 이하면 null로 바꾼다.
- 빈 문자열 `memo`·`dueDate`·`dueTime`은 null로 바꾼다.

기능별 고정 규칙(어떤 필드가 항상 null인지 등)은 각 기능 명세에서 정한다.
