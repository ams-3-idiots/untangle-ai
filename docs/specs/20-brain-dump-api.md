# 브레인덤프 API 호환

> 관련 GitHub Issue: [#20](https://github.com/ams-3-idiots/untangle-ai/issues/20)

## 1. 핵심 결정

### 1.1 전체 흐름

```text
[세션 생성]
  ↓
[sessionId 발급]
  ↓
[브레인덤프 요청]
  ↓
[요청한 대화 세션이 존재하는지 확인]
  ↓
[LLM에 요청을 보내 할 일 추출]
  ↓
[개인정보 복원]
  ↓
[필드 정규화·중복 제거]
  ↓
[추출한 할 일이 사용자 원문에 있었는지 검증]
  ↓
<할 일 후보가 있는가?>
  ├─ 있음   → [최대 5개 tasks와 proposalId 반환]
  └─ 없음   → [빈 tasks와 재입력 안내 반환]
```

### 1.2 결정 사항

- `sessionId`는 서버가 덤프 요청에 사용할 세션을 찾을 때 사용한다.
- `proposalId`는 앱과 로그에서 반환된 제안이 어느 세션의 결과인지 식별할 때
  사용하며, `sessionId`와 항상 같다.
- `tasks`는 최대 5개이며, `tasks: []`는 오류가 아닌 정상 응답이다.
- `sourceExcerpt`는 요청 `text`의 부분 문자열임을 서버가 검증한다. 검증은
  개인정보 마스킹을 복원한 원문 기준으로 한다.
- 덤프는 세션의 이전 대화를 프롬프트 맥락으로 쓰지 않고 요청 한 건만으로
  처리한다. 세션은 요청 자격과 `proposalId` 발급에만 쓰며, 성공한 덤프는
  대화를 쌓지 않고 세션 수명만 갱신한다.
- `Idempotency-Key`는 덤프에만 적용한다. 세션 생성은 LLM을 호출하지 않으므로
  대상이 아니다.

## 2. 상세 설계

### 2.1 세션 생성

`POST /api/v1/ai-sessions` → `201`

- 본문 없이 호출하며 `{"sessionId": "<uuid>"}`를 반환한다.
- 덤프는 이 API로 만든 세션의 `sessionId`를 경로에 실어 호출한다.
- 덤프는 살아 있는 세션이면 용도 구분 없이 동작한다. 같은 세션의 이전 대화를
  프롬프트 맥락으로 쓸지는 계약이 아니며 구현에서 정한다.

### 2.2 덤프 요청

`POST /api/v1/ai-sessions/{sessionId}/dump` → `200`

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

### 2.3 덤프 응답

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

`TaskDraft`의 공통 정의와 정규화 규칙은
`docs/specs/17-spring-compatible-http-base.md`를 따르고, 덤프에서는 다음 규칙을
더한다.

| 필드 | 덤프 규칙 |
| --- | --- |
| `memo` | 모델 제안 (없으면 null) |
| `dueDate`·`dueTime` | 모델 제안 (`clientNow` 기준 환산) |
| `reminderMinutesBefore` | 모델 제안 |
| `importance`·`estimatedMinutes` | 모델 제안 — 정규화로 null이 될 수 있음 |
| `sourceExcerpt` | 입력 `text`의 부분 문자열임을 서버가 검증 — 아니면 null |

- **`tasks: []`는 정상 `200` 응답이다.**
  이때 `assistantText`에 재입력 안내를 담아 보낸다.
  결과도 비고 안내문도 없는 모델 응답은 `503`으로 처리한다.
- `sourceExcerpt`는 할 일이 추출된 근거를 추적하는 필드다. 모델이 입력에 없는
  문장을 지어낼 수 있으므로, 서버가 요청 `text`에 실제로 포함된 문자열인지
  확인한다.
  출처가 없다면 null로 바꾼다. 이 확인은 개인정보 마스킹을 복원한 원문
  기준으로 한다.
- `assistantText`는 앞뒤 공백을 없앤 값을 내보낸다. `tasks`가 있으면 빈
  문자열일 수 있다.

### 2.4 서버 처리 순서

1. 경로의 `sessionId`로 세션을 찾는다. 없거나 만료됐으면 `404`이며 LLM을
   호출하지 않는다.
2. 같은 `Idempotency-Key`의 성공 응답이 있으면 그대로 돌려준다.
3. rate limit을 확인한다. 2에서 재사용한 응답은 한도를 소비하지 않는다.
4. 마스킹한 요청으로 LLM을 호출하고, 응답의 마스킹을 원문으로 되돌린다.
5. `sourceExcerpt` 검증 → 공통 정규화 → `existingTaskTitles` 중복 제거 →
   최대 5개 순서로 후보를 정리한다. 중복을 상한보다 먼저 걷어내야 이미 있는
   할 일 때문에 후보 수가 줄지 않는다.
6. 응답을 얻은 뒤에만 세션 수명을 갱신한다. 2에서 재사용한 응답도 세션을 쓴
   성공 요청이므로 갱신 대상이다.

모델이 `dueDate`·`dueTime` 형식처럼 정규화가 다루지 않는 계약을 어기면 쓸 수
없는 응답이므로 `503`으로 처리한다.

### 2.5 호환성 테스트 사례

외부 OpenAI 호출 없이 fake LLM으로 검증한다.

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | 본문 없이 세션 생성 | `201`과 `sessionId` |
| T-02 | 살아 있는 세션에 덤프 요청 | `200`, `proposalId`가 경로의 `sessionId`와 같음 |
| T-03 | 발급된 적 없는 세션, UUID 형식이 아닌 `sessionId` | `404` ProblemDetail |
| T-04 | 공백 `text`, `existingTaskTitles` 누락, 길이 초과 | `422` ProblemDetail |
| T-05 | 후보를 뽑지 못한 모델 응답 | `200`과 빈 `tasks`, 비공백 `assistantText` |
| T-06 | 후보도 안내 문구도 없는 모델 응답 | `503` ProblemDetail |
| T-07 | 입력에 없는 `sourceExcerpt`, 범위 밖 `importance`·`estimatedMinutes` | 해당 필드만 null |
| T-08 | `existingTaskTitles`와 같은 제목, 후보 6개 이상 | 중복 제거 후 최대 5개 |
| T-09 | 같은 `Idempotency-Key`로 재시도 | 같은 응답 재사용, LLM 호출 1회 |
