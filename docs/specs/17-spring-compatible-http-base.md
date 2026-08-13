# Spring 호환 공통 HTTP 기반

> 관련 GitHub Issue: [#17](https://github.com/ams-3-idiots/untangle-ai/issues/17)

구현 전 초안이다. 구현 과정에서 확정한 내용을 이 문서에 반영한다.

지원 API 전체가 공유하는 HTTP 기반 계약 — 경로, 공통 스키마, 헤더, 오류
응답 — 을 정한다. 호환성 기준의 정본은 Spring 서버 코드(`../server`, develop
최신)와 `../server/docs/mobile-api-contract.md`다. Android·iOS 앱은 착수
전이므로 앱이 의존할 계약의 기준은 위 두 출처다.

## 1. 핵심 결정

- 요청·응답 DTO의 와이어 필드 이름은 Spring과 동일한 camelCase를 유지한다.
  와이어 필드 이름은 HTTP 요청·응답 JSON에 실제로 실리는 키 이름을 말한다.
- 모든 오류 응답 본문은 RFC 9457 ProblemDetail로 통일한다.
- `422`는 요청 형식(타입·필수값·길이) 검증 실패 전용이다. 규칙 위반을 `422`로
  표현하지 않으며, FastAPI 기본 `422` 본문(`{"detail": [...]}`) 대신
  ProblemDetail로 변환한다.
- 도메인 오류는 `404`·`429`·`503`에 매핑한다. `400`·`502`는 지원 경로 계약에서
  쓰지 않는다.
- 앱은 **상태 코드로만 분기**한다. `title`·`detail` 문구는 사람이 읽는 참고
  정보이며 정확한 문자열은 계약이 아니다.
- `Authorization` 헤더는 허용하되 검증·사용자 식별에 쓰지 않는다.
  `401`·`403`을 반환하지 않는다.
- 모든 응답에 `X-Request-Id`를 실어 요청을 추적할 수 있게 한다.

## 2. 상세 설계

### 2.1 지원 경로

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| POST | `/api/v1/ai-sessions` | 세션 생성 |
| POST | `/api/v1/ai-sessions/{sessionId}/dump` | 브레인덤프 |
| POST | `/api/v1/ai-sessions/decompose` | 쪼개기 시작 |
| POST | `/api/v1/ai-sessions/{sessionId}/decompose` | 쪼개기 이어가기 |

- 경로의 `{sessionId}`가 UUID 형식이 아니면 "세션 없음"과 동일하게 `404`로
  처리한다.

### 2.2 공통 헤더 규칙

#### Authorization

- 헤더가 있어도, 없어도, 값이 무엇이어도 요청 처리 결과가 달라지지 않는다.
- JWT 검증·사용자 식별에 사용하지 않으며 로그에도 남기지 않는다.
- 새 AI 서버는 어떤 경우에도 `401`·`403`을 반환하지 않는다.

#### X-Request-Id

서버 로그에서 특정 요청을 추적하는 식별자다. 앱이 버그 리포트·문의에 응답
헤더의 이 값을 첨부하면 해당 요청의 서버 로그를 바로 찾을 수 있다.

- 요청 헤더 값이 `[A-Za-z0-9._-]{1,64}` 패턴에 맞으면 그대로 사용하고, 없거나
  패턴을 벗어나면 서버가 UUID를 생성한다.
- 결정된 값은 모든 응답(오류 포함)의 `X-Request-Id` 헤더에 싣고, 서버 로그의
  요청 추적 식별자로 쓴다.

`Idempotency-Key` 규칙은 `docs/specs/18-ttl-session-idempotency.md`에서 정한다.

### 2.3 공통 오류 계약

모든 오류 본문은 RFC 9457 ProblemDetail이다. `Content-Type`은
`application/problem+json`을 사용한다.

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

### 2.4 TaskDraft 공통 스키마

덤프의 `tasks[]`와 쪼개기의 `items[]`가 공유하는 할 일 제안 DTO다.
**8개 필드는 값이 없어도 키를 생략하지 않고 `null`로 직렬화한다.**

| 필드 | 타입 | 의미 (null = 단서 없음) |
| --- | --- | --- |
| `title` | string | 할 일 제목 — null·빈 문자열 없이 항상 비공백 |
| `memo` | string \| null | 제목에 담지 못한 보충 메모 |
| `importance` | int(1\|2\|3) \| null | 중요도 — 1=높음, 2=중간, 3=낮음 |
| `estimatedMinutes` | int(>0) \| null | 예상 소요 시간(분) |
| `dueDate` | string(`yyyy-MM-dd`) \| null | 마감 날짜 |
| `dueTime` | string(`HH:mm`) \| null | 마감 시각 (24시간제) |
| `reminderMinutesBefore` | int(10\|30\|60\|180\|1440) \| null | 마감 전 알림 시점(분) — null이면 알림 없음 |
| `sourceExcerpt` | string \| null | 이 할 일이 추출된 근거 원문 일부 |

서버는 모델 출력을 그대로 내보내지 않고 다음 정규화를 거친다.

- 제목이 공백뿐인 항목은 버린다.
- 제목의 `strip + 소문자` 결과가 같으면 첫 항목만 남긴다(순서 유지).
- `importance`가 1~3 밖이면 null, `estimatedMinutes`가 0 이하면 null,
  `reminderMinutesBefore`가 허용값 밖이면 null로 바꾼다.
- 빈 문자열 `memo`·`dueDate`·`dueTime`은 null로 바꾼다.

기능별 고정 규칙(어떤 필드가 항상 null인지 등)은 각 기능 명세에서 정한다.

### 2.5 호환성 테스트 사례

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | 지원 4경로 성공 응답 | 응답 헤더에 유효한 `X-Request-Id` 존재 |
| T-02 | 유효한 `X-Request-Id`(영숫자·`.`·`_`·`-`, 64자 이내)를 요청에 포함 | 같은 값이 응답 헤더로 에코 |
| T-03 | 무효한 `X-Request-Id`(65자 이상 또는 허용 외 문자) 포함 | 서버 생성 UUID로 대체되어 응답 |
| T-04 | `Authorization` 헤더 없이 요청 | 정상 처리 (`401` 아님) |
| T-05 | `Authorization: Bearer <임의 문자열>` 포함 요청 | 헤더 없는 경우와 동일한 정상 처리 |
| T-06 | 검증 실패 응답 본문 | `422` + `{type, title: "Validation failed", status: 422, detail}` ProblemDetail, `detail`에 필드 경로 포함, `Content-Type: application/problem+json` |
| T-07 | UUID 형식이 아닌 `sessionId` 경로 | `404` (`422` 아님) |
