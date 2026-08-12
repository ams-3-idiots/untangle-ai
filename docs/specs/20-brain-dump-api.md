# 브레인덤프 API 호환

> 관련 GitHub Issue: [#20](https://github.com/ams-3-idiots/untangle-ai/issues/20)

구현 전 초안이다. 구현 과정에서 확정한 내용을 이 문서에 반영한다.

## 1. 핵심 결정

- 세션 생성과 덤프의 경로·요청·응답·상태 코드를 Spring과 동일하게 유지한다.
- 응답의 `proposalId`는 세션의 `sessionId`와 항상 같은 값이다 (로깅·식별용).
- `tasks`는 최대 5개이며, `tasks: []`는 오류가 아닌 정상 응답이다.
- `sourceExcerpt`는 요청 `text`의 부분 문자열임을 서버가 검증한다. 검증은
  개인정보 마스킹을 복원한 원문 기준으로 한다.

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

- **`tasks: []`는 정상 `200` 응답이다** (감정·잡담뿐이라 추출 불가). 이때
  `assistantText`가 재입력 안내를 담는다. 결과도 비고 안내문도 없는 모델 응답은
  `503`으로 처리한다.
- `sourceExcerpt`는 할 일이 추출된 근거를 추적하는 필드다. 모델이 입력에 없는
  문장을 지어낼 수 있으므로, 서버가 요청 `text`에 실제로 포함된 문자열인지
  확인하고 아니면 null로 바꾼다. 이 확인은 개인정보 마스킹을 복원한 원문
  기준으로 한다.

### 2.4 호환성 테스트 사례

외부 OpenAI 호출 없이 fake LLM으로 검증한다.

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | `POST /ai-sessions` | `201` + `{"sessionId": <uuid>}` |
| T-02 | 정상 덤프 | `200`, `proposalId` == 경로 `sessionId`, `tasks` ≤ 5개, 각 항목에 `TaskDraft` 8필드 모두 존재 |
| T-03 | 추출할 것이 없는 입력 | `200` + `tasks: []` + 비공백 `assistantText` |
| T-04 | `text` 공백·누락·8000자 초과 / `existingTaskTitles` null·201개·항목 501자 / `clientNow` 41자 | 각각 `422` |
| T-05 | 모델이 입력에 없는 `sourceExcerpt`를 반환 | 해당 필드 null로 정규화 |
| T-06 | 모델이 `importance` 0, `estimatedMinutes` -5, `reminderMinutesBefore` 15, 빈 문자열 `memo`·`dueDate` 반환 | 모두 null로 정규화, 제목 중복(`strip+소문자`)은 첫 항목만 유지 |
| T-07 | 결과도 비고 안내문도 없는 모델 응답 | `503` |
