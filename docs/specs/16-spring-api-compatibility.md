# Spring 호환 AI API 통신 계약과 호환성 기준

> 관련 GitHub Issue: [#16](https://github.com/ams-3-idiots/untangle-ai/issues/16)

Spring 서버의 브레인덤프와 할 일 쪼개기를 FastAPI로 이전할 때 모바일 앱이
요청 경로와 요청·응답 DTO를 바꾸지 않고 쓸 수 있도록, 지원 API의 통신 계약과
호환성 기준을 이 문서 한 곳에서 확정한다. 후속 구현 이슈들은 이 문서를 공통
기준으로 사용한다.

이 문서는 앱이 관찰할 수 있는 HTTP 계약(경로·헤더·본문·상태 코드·오류)만
확정한다. 저장소 구조, LLM 클라이언트 설계 같은 내부 구현은 후속 이슈에서
정한다.

## 1. 핵심 결정

### 1.1 호환성 기준의 정본

| 출처 | 역할 |
| --- | --- |
| Spring 서버 코드 (`../server`, develop 최신) | 실제 동작의 정본 |
| `../server/docs/mobile-api-contract.md` | 앱 온보딩용 계약서 |

Android·iOS 앱은 착수 전이므로 앱이 의존할 계약의 기준은 위 두 출처다.

### 1.2 유지하는 계약

상세 값은 2장에 있다.

- 지원 4개 경로와 각 경로의 성공 상태 코드
- 요청·응답 DTO의 와이어 필드 이름과 필수 여부, 길이·개수 제한.
  와이어 필드 이름은 HTTP 요청·응답 JSON에 실제로 실리는 키 이름을 말하며,
  Spring과 동일한 camelCase를 유지한다.
- `TaskDraft` 8개 필드 전부 직렬화, 기능별 null 의미 유지
- `proposalId == sessionId` — 모든 응답에서 두 값은 항상 같다 (로깅·식별용)
- RFC 9457 ProblemDetail 오류 본문과 `404`·`422`·`429`·`503` 상태 코드
- `Idempotency-Key` — 같은 키 재요청은 LLM을 다시 호출하지 않고
  같은 응답을 재전송
- `X-Request-Id` — 서버가 모든 응답에 부여하는 요청 추적 ID.
  앱의 버그 리포트·문의에 실린 이 값으로 서버 로그에서 해당 요청을 찾는다.
- 결과 최대 5개, 쪼개기 질문 최대 5회, 질문 선택지 2~4개 상한
- 덤프의 정상 빈 결과 (`tasks: []`)
- 개인정보 처리 — 앱은 원문을 그대로 보내고, 응답에서는 마스킹 없이 원문이
  복원되어 온다

### 1.3 제거하는 계약

| 항목 | 새 AI 서버의 결정 |
| --- | --- |
| JWT 인증 | `Authorization` 헤더를 허용하되 검증·사용자 식별에 쓰지 않는다. `401`을 반환하지 않는다 |
| 세션 소유권 | 소유권 검사 없음 — `sessionId` 자체가 접근 자격 |
| `single-add`·`suggest` | 미제공 (`404`) |
| `report` | AI 서버 범위 밖 — 기존 Spring 서버에 남는다 |
| 사용자별 사용량 쿼터 | 사용자별 쿼터 없음 — 프로세스 단위 보호 한도로 대체하고 `429` 계약은 유지 |
| DB 영구 저장 | 세션·대화·멱등 응답을 프로세스 메모리에만 보관 |

### 1.4 새로 정의하는 동작

| 항목 | Spring | 새 AI 서버 |
| --- | --- | --- |
| 세션 수명 | TTL 없음 | 마지막 성공 요청 후 30분 (성공 요청마다 갱신). 만료·재시작 시 `404` |
| 멱등 캐시 | user+key 스코프, 기록 후 10분 | 키 단독 스코프, 마지막 사용 후 30분 |
| 질문 상한 강제 | 프롬프트 지시 수준 | 서버가 구조적으로 강제 — 질문 턴 5회 도달 후에는 반드시 분해 턴 |
| LLM provider | Anthropic Claude | OpenAI structured output — 응답 계약은 동일 유지 |
| 검증 실패 본문 | Spring ProblemDetail | FastAPI 기본 `422` 본문 대신 ProblemDetail로 변환 |

### 1.5 오류 응답 원칙

- 지원 경로의 모든 오류 응답 본문은 RFC 9457 ProblemDetail로 통일한다.
- `422`는 요청 형식(타입·필수값·길이) 검증 실패 전용이다. 규칙 위반을
  `422`로 표현하지 않는다.
- 도메인 오류는 `404`(세션 없음·만료), `429`(보호 한도 초과), `503`(외부 AI
  실패)에 매핑한다. `400`·`502`는 지원 경로 계약에서 쓰지 않는다.
- 앱은 **상태 코드로만 분기**한다. `title`·`detail` 문구는 사람이 읽는 참고
  정보이며 정확한 문자열은 계약이 아니다.

## 2. 상세 설계

### 2.1 지원 경로

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| POST | `/api/v1/ai-sessions` | 세션 생성 |
| POST | `/api/v1/ai-sessions/{sessionId}/dump` | 브레인덤프 |
| POST | `/api/v1/ai-sessions/decompose` | 쪼개기 시작 |
| POST | `/api/v1/ai-sessions/{sessionId}/decompose` | 쪼개기 이어가기 |

- 위 4개가 새 AI 서버의 공개 계약 전부다. 그 외 경로는 라우터에 등록하지
  않으며 `404`가 된다. 계약 밖 경로의 `404` 본문 형식은 보장하지 않는다.
- 경로의 `{sessionId}`가 UUID 형식이 아니면 "세션 없음"과 동일하게 `404`로
  처리한다.

### 2.2 공통 헤더 규칙

#### Authorization

- 헤더가 있어도, 없어도, 값이 무엇이어도 요청 처리 결과가 달라지지 않는다.
- JWT 검증·사용자 식별에 사용하지 않으며 로그에도 남기지 않는다.
- 새 AI 서버는 어떤 경우에도 `401`·`403`을 반환하지 않는다.

#### Idempotency-Key

LLM을 호출하는 3개 경로(덤프, 쪼개기 시작·이어가기)에서 사용한다.
세션 생성은 LLM을 호출하지 않으므로 대상이 아니다.

- 선택 헤더다. 없거나 공백이면 멱등 처리를 우회한다(재시도가 매번 LLM을
  호출한다).
- 값 형식은 검증하지 않는다 — 비공백 문자열이면 수용한다. 앱 생성 UUID를
  권장한다.
- 성공 응답만 캐시한다. 같은 키의 재요청은 LLM을 다시 호출하지 않고 저장된
  응답 본문을 그 경로의 성공 상태 코드로 재전송한다.
- 오류 응답(`404`·`422`·`429`·`503`)은 캐시하지 않는다 — 같은 키로 재시도하면
  다시 실행한다.
- 요청 본문은 비교하지 않는다 — 같은 키에 다른 본문을 보내면 이전 응답이
  재전송된다. 내용이 다른 새 요청은 반드시 새 키를 쓴다.
- 캐시 항목은 마지막 사용 후 30분 보관한다. 크기 상한과 정리 정책은 후속
  구현에서 정한다.

#### X-Request-Id

서버 로그에서 특정 요청을 추적하는 식별자다. 앱이 버그 리포트·문의에 응답
헤더의 이 값을 첨부하면 해당 요청의 서버 로그를 바로 찾을 수 있다.

- 요청 헤더 값이 `[A-Za-z0-9._-]{1,64}` 패턴에 맞으면 그대로 사용하고, 없거나
  패턴을 벗어나면 서버가 UUID를 생성한다.
- 결정된 값은 모든 응답(오류 포함)의 `X-Request-Id` 헤더에 싣고, 서버 로그의
  요청 추적 식별자로 쓴다.

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

### 2.4 TaskDraft 계약

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

기능별 고정 규칙:

| 필드 | 덤프 | 쪼개기 |
| --- | --- | --- |
| `memo` | 모델 제안 (없으면 null) | **항상 null** |
| `dueDate`·`dueTime` | 모델 제안 (`clientNow` 기준 환산) | **항상 null** |
| `reminderMinutesBefore` | 모델 제안 | **항상 null** |
| `sourceExcerpt` | 입력 `text`의 **부분 문자열임을 서버가 검증** — 아니면 null | **항상 대상 제목** (개행을 공백으로 접고 앞뒤 공백을 없앤 `target.title`) |
| `importance`·`estimatedMinutes` | 모델 제안 — 정규화로 null이 될 수 있음 | 동일 |

### 2.5 세션·멱등성·보호 한도

#### 세션 수명

- 세션은 프로세스 메모리에만 존재한다. **마지막 성공 요청 후 30분**이 지나면
  만료되며, 세션을 사용하는 요청이 성공할 때마다 수명이 갱신된다.
- 만료된 세션, 발급된 적 없는 세션, 프로세스 재시작·배포로 사라진 세션은 모두
  같은 `404`로 응답한다.
- `POST /api/v1/ai-sessions`는 본문 없이 호출하며 `201`과 새 UUID를 반환한다.
  쪼개기는 시작 API가 세션을 직접 만들어 돌려주므로 별도 생성이 필요 없다.
- 모든 응답의 `proposalId`는 해당 세션의 `sessionId`와 같은 값이다.

#### 세션과 대화 상태

- 쪼개기 대화(시작 기록, 질문·답 이력, 직전 분해 결과)는 서버가 세션에 보관하고
  복원한다. 앱은 이력을 관리하지 않고 **매 턴 이번 발화 하나만** 보낸다.
- 쪼개기 이어가기는 쪼개기 시작으로 만들어진 세션에서만 동작한다. 시작 기록이
  없는 세션에 이어가기를 호출하면 `404`다.
- 덤프는 살아 있는 세션이면 용도 구분 없이 동작한다. 같은 세션의 이전 대화를
  프롬프트 맥락으로 쓸지는 계약이 아니며 후속 구현에서 정한다.

#### 보호 한도

- DB 없이 동작하는 rate limit과 세션 수·턴 수·대화 크기·멱등 캐시 크기 상한을
  둔다. 구체적인 값과 측정 기준은 후속 구현에서 정한다.
- 어떤 보호 한도든 초과 시 응답은 `429` ProblemDetail 하나로 통일한다.

### 2.6 브레인덤프 API

`POST /api/v1/ai-sessions/{sessionId}/dump` → `200`

#### 요청

```json
{
  "text": "졸업논문 중간발표가 2주 뒤인데 아직 데이터 정리도 안 했고 …",
  "existingTaskTitles": ["교수님 미팅 준비"],
  "clientNow": "2026-07-09T22:00:00+09:00"
}
```

| 필드 | 설명 | 필수 | 제약 |
| --- | --- | --- | --- |
| `text` | 할 일을 추출할 원문 — 사용자가 쏟아낸 생각 뭉치 | 필수 | 비공백, 최대 8000자 |
| `existingTaskTitles` | 앱에 이미 있는 할 일 제목 목록 — 중복 제안 방지 기준 | 필수 (빈 배열 허용, null 불가) | 최대 200개, 항목당 최대 500자 |
| `clientNow` | 앱 로컬 현재 시각 — "다음 주까지" 같은 상대 기한의 환산 기준 | 선택 | 최대 40자, ISO-8601 권장. 형식 자체는 검증하지 않는다 |

#### 응답

```json
{
  "proposalId": "cace6837-…",
  "tasks": [
    {
      "title": "논문 데이터 정리하기",
      "memo": "중간발표 전까지 완료 필요",
      "importance": 1,
      "estimatedMinutes": 300,
      "dueDate": "2026-07-23",
      "dueTime": null,
      "reminderMinutesBefore": null,
      "sourceExcerpt": "아직 데이터 정리도 안 했고"
    }
  ],
  "assistantText": "일단 눈에 보이는 것부터 나눠봤어요."
}
```

| 필드 | 규칙 |
| --- | --- |
| `proposalId` | 경로의 `sessionId`와 같은 값 |
| `tasks` | `TaskDraft` 배열, **최대 5개**, null이 아님(빈 배열 가능). 중복 제안 방지 기준은 요청의 `existingTaskTitles` |
| `assistantText` | 필드는 항상 존재. `tasks: []`일 때는 비공백이 보장된다(재입력 안내) |

- **`tasks: []`는 정상 `200` 응답이다** (감정·잡담뿐이라 추출 불가). 이때
  `assistantText`가 재입력 안내를 담는다. 결과도 비고 안내문도 없는 모델 응답은
  `503`으로 처리한다.
- `sourceExcerpt`는 할 일이 추출된 근거를 추적하는 필드다. 모델이 입력에 없는
  문장을 지어낼 수 있으므로, 서버가 요청 `text`에 실제로 포함된 문자열인지
  확인하고 아니면 null로 바꾼다. 이 확인은 개인정보 마스킹을 복원한 원문
  기준으로 한다.

### 2.7 할 일 쪼개기 API

- 시작: `POST /api/v1/ai-sessions/decompose` → `201` (세션을 직접 생성해 반환)
- 이어가기: `POST /api/v1/ai-sessions/{sessionId}/decompose` → `200`

#### 시작 요청

```json
{
  "target": { "title": "운동 시작하기", "notes": null },
  "instruction": null
}
```

| 필드 | 설명 | 필수 | 제약 |
| --- | --- | --- | --- |
| `target` | 쪼갤 할 일 | 필수 | 객체 |
| `target.title` | 쪼갤 할 일의 제목 | 필수 | 비공백, 최대 500자 |
| `target.notes` | 대상에 대한 보충 메모 | 선택 | 최대 4000자 |
| `instruction` | 분해 방식 지시 — 있으면 질문 없이 바로 분해한다 | 선택 | 최대 2000자 |

#### 이어가기 요청

```json
{ "message": "체력 증진이 목적이야" }
```

| 필드 | 설명 | 필수 | 제약 |
| --- | --- | --- | --- |
| `message` | 이번 턴의 사용자 발화 — 선택지 칩 텍스트 또는 자유 입력 | 필수 | 비공백, 최대 2000자 |

#### 응답 (시작·이어가기 공통) — `items`의 null 여부로 턴 구분

```json
{
  "sessionId": "cace6837-…",
  "proposalId": "cace6837-…",
  "items": null,
  "options": ["체중 감량", "체력 증진", "스트레스 해소"],
  "firstStep": null,
  "assistantText": "운동을 시작하려는 주된 목적이 뭔가요?"
}
```

| 필드 | 질문 턴 | 분해 턴 |
| --- | --- | --- |
| `items` | **null** | `TaskDraft` 배열 1~5개, 배열 순서 = 실행 순서 |
| `options` | 선택지 2~4개 | **null** |
| `firstStep` | null | null |
| `assistantText` | AI의 질문 한 문장 | 한두 문장 설명 |
| `sessionId`·`proposalId` | 항상 존재, 같은 값 | 항상 존재, 같은 값 |

- **`firstStep` 필드는 유지하되 값은 언제나 null이다.** '지금 할 첫 단계'는
  `items[0]`으로 온다. 분해 턴의 `items`가 비어 있는 모델 응답은 `503`으로
  처리한다.
- 질문 턴의 조건: `assistantText`가 비공백이고 중복 제거 후 `options`가 2개
  이상. 선택지는 최대 4개까지만 내려보낸다.
- 질문은 대화 전체에서 최대 5회다. 질문 턴 5회에 도달하면 이후 응답은 반드시
  분해 턴이다.
- 분해 턴을 받은 뒤에도 같은 세션에 "더 잘게 쪼개줘"를 보내면 서버가 직전
  목록을 기억하고 전체를 더 잘게 재구성해 돌려준다(항목 수 상한 5개 동일).
- "그냥 쪼개줘"·"모르겠어" 같은 발화에는 즉시 분해로 넘어간다.

### 2.8 현행 FastAPI 계약과의 차이

현행 FastAPI 서버는 아래 항목이 모두 다르며, 이 문서의 지원 계약으로
대체된다. 기존 경로·DTO·오류 형식은 후속 정리 작업에서 제거한다.

| 항목 | 현행 FastAPI | 지원 계약 (이 문서) |
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

### 2.9 호환성 테스트 사례

후속 구현이 재사용할 테스트 사례다. 외부 OpenAI 호출 없이 fake LLM으로
검증한다(`tests/conftest.py`의 `client`·`fake_llm` fixture 패턴 재사용,
배치는 `docs/conventions/testing.md`를 따른다).

#### 공통 (헤더·오류 형식)

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | 지원 4경로 성공 응답 | 응답 헤더에 유효한 `X-Request-Id` 존재 |
| T-02 | 유효한 `X-Request-Id`(영숫자·`.`·`_`·`-`, 64자 이내)를 요청에 포함 | 같은 값이 응답 헤더로 에코 |
| T-03 | 무효한 `X-Request-Id`(65자 이상 또는 허용 외 문자) 포함 | 서버 생성 UUID로 대체되어 응답 |
| T-04 | `Authorization` 헤더 없이 요청 | 정상 처리 (`401` 아님) |
| T-05 | `Authorization: Bearer <임의 문자열>` 포함 요청 | 헤더 없는 경우와 동일한 정상 처리 |
| T-06 | 검증 실패 응답 본문 | `422` + `{type, title: "Validation failed", status: 422, detail}` ProblemDetail, `detail`에 필드 경로 포함, `Content-Type: application/problem+json` |

#### 세션 수명

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-07 | `POST /ai-sessions` | `201` + `{"sessionId": <uuid>}` |
| T-08 | 발급된 적 없는 UUID로 덤프·이어가기 | `404` ProblemDetail (`title: "Not found"`) |
| T-09 | 마지막 성공 요청 후 30분 경과한 세션 사용 | `404` |
| T-10 | 30분 이내 성공 요청으로 세션 수명 갱신 | 갱신 이후 30분까지 사용 가능 |
| T-11 | 저장소 초기화(재시작 시뮬레이션) 후 기존 세션 사용 | `404` |
| T-12 | UUID 형식이 아닌 `sessionId` 경로 | `404` (`422` 아님) |

#### 브레인덤프

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-13 | 정상 덤프 | `200`, `proposalId` == 경로 `sessionId`, `tasks` ≤ 5개, 각 항목에 `TaskDraft` 8필드 모두 존재 |
| T-14 | 추출할 것이 없는 입력 | `200` + `tasks: []` + 비공백 `assistantText` |
| T-15 | `text` 공백·누락·8000자 초과 / `existingTaskTitles` null·201개·항목 501자 / `clientNow` 41자 | 각각 `422` |
| T-16 | 모델이 입력에 없는 `sourceExcerpt`를 반환 | 해당 필드 null로 정규화 |
| T-17 | 모델이 `importance` 0, `estimatedMinutes` -5, `reminderMinutesBefore` 15, 빈 문자열 `memo`·`dueDate` 반환 | 모두 null로 정규화, 제목 중복(`strip+소문자`)은 첫 항목만 유지 |

#### 할 일 쪼개기

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-18 | 시작(질문 턴) | `201`, `sessionId == proposalId`, `items: null`, `options` 2~4개, `firstStep: null`, 비공백 `assistantText` |
| T-19 | `instruction`을 포함한 시작 | 질문 없이 바로 분해 턴 |
| T-20 | `target` 누락 / `target.title` 공백·501자 / `notes` 4001자 / `instruction` 2001자 | 각각 `422` |
| T-21 | 시작 응답의 `sessionId`로 이어가기 (`message` 하나만 전송) | `200`, 대화가 이어짐 |
| T-22 | 분해 턴 | `items` 1~5개, `options: null`, `firstStep: null`, 각 항목 `memo`·`dueDate`·`dueTime`·`reminderMinutesBefore` null, `sourceExcerpt`는 개행·앞뒤 공백을 정규화한 `target.title` |
| T-23 | 질문 턴 5회 도달 후 이어가기 | 응답은 반드시 분해 턴 |
| T-24 | 분해 턴 후 같은 세션에 "더 잘게 쪼개줘" | 직전 목록 기반 재분해, `items` ≤ 5개 |
| T-25 | 쪼개기 시작 기록이 없는 세션(`POST /ai-sessions`로 생성)에 이어가기 | `404` |
| T-26 | `message` 공백·2001자 | `422` |

#### 멱등성·보호 한도

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-27 | 같은 `Idempotency-Key`로 같은 요청 2회 | 본문 동일, LLM 호출 1회, 성공 상태 코드는 경로 고유 값 유지(시작 `201`, 덤프·이어가기 `200`) |
| T-28 | 다른 키로 2회 | LLM 2회 호출, 독립 응답 |
| T-29 | 키 없이 2회 | 캐시 미사용 — LLM 2회 호출 |
| T-30 | 1회차가 `503`으로 실패한 뒤 같은 키로 재시도 | 오류는 캐시되지 않아 재실행 |
| T-31 | 보호 한도(rate limit 등) 초과 | `429` ProblemDetail (`title: "Too many requests"`) |
| T-32 | 멱등 캐시 항목의 마지막 사용 후 30분 경과, 같은 키 재요청 | 캐시 만료 — 재실행 |

#### 외부 AI 실패·개인정보

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-33 | provider 설정(API key 등) 누락 | `503` ProblemDetail (`title: "AI service unavailable"`) |
| T-34 | timeout·네트워크·SDK 예외 | `503` ProblemDetail |
| T-35 | 스키마를 벗어난 모델 응답, 분해 턴의 빈 `items`, 빈 덤프 결과 + 빈 안내문 | `503` ProblemDetail |
| T-36 | 전화번호가 포함된 입력 | LLM에 전달되는 페이로드에 원문 없음(마스킹), API 응답 필드에는 원문 복원 |
| T-37 | 오류 응답(`404`·`422`·`429`·`503`) 및 애플리케이션 로그 | 사용자 입력·대화·프롬프트·모델 원문 미포함 |

#### 미지원 경로

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-38 | `single-add`·`suggest`·기존 `/api/v1/ai/brain-dump`·`/api/v1/ai/task-breakdown` 호출 | `404` — 지원 4경로 외에는 노출되지 않는다 |

### 2.10 제외 범위

- FastAPI 코드와 테스트 구현
- 모바일 앱의 요청 경로·DTO 변경
- `single-add`, `suggest`, `report`, 인증의 계약 정의
- 공개 진입점에서 AI 경로만 FastAPI로 분기하는 라우팅·인프라 설계
- rate limit·상한의 구체적 수치
- 프롬프트 내용, LLM 모델 선택, 마스킹 대상 항목의 상세
