# 할 일 쪼개기 API 호환

> 관련 GitHub Issue: [#21](https://github.com/ams-3-idiots/untangle-ai/issues/21)

구현 전 초안이다. 구현 과정에서 확정한 내용을 이 문서에 반영한다.

## 1. 핵심 결정

- 시작·이어가기의 경로·요청·응답·상태 코드를 Spring과 동일하게 유지한다.
- `items`의 null 여부로 질문 턴과 분해 턴을 구분한다. `firstStep` 필드는
  유지하되 값은 언제나 null이다.
- 질문은 대화 전체에서 최대 5회다. 5회 도달 후에는 서버가 분해 턴을 구조적으로
  강제한다 (Spring은 프롬프트 지시 수준).
- 앱은 대화 이력을 관리하지 않고 매 턴 이번 발화 하나만 보낸다 — 대화는 서버
  세션이 보관·복원한다.
- 쪼개기 이어가기는 쪼개기 시작으로 만들어진 세션에서만 동작한다.

## 2. 상세 설계

### 2.1 시작 요청

`POST /api/v1/ai-sessions/decompose` → `201` (세션을 직접 생성해 반환 — 별도
세션 생성이 필요 없다)

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

### 2.2 이어가기 요청

`POST /api/v1/ai-sessions/{sessionId}/decompose` → `200`

```json
{ "message": "체력 증진이 목적이야" }
```

| 필드 | 설명 | 필수 | 제약 |
| --- | --- | --- | --- |
| `message` | 이번 턴의 사용자 발화 — 선택지 칩 텍스트 또는 자유 입력 | 필수 | 비공백, 최대 2000자 |

### 2.3 응답 (시작·이어가기 공통) — `items`의 null 여부로 턴 구분

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
- 쪼개기 시작 기록이 없는 세션(세션 생성 API로 만든 세션 등)에 이어가기를
  호출하면 `404`다.

`TaskDraft`의 공통 정의와 정규화 규칙은
`docs/specs/17-spring-compatible-http-base.md`를 따르고, 쪼개기에서는 다음
규칙을 더한다.

| 필드 | 쪼개기 규칙 |
| --- | --- |
| `memo`·`dueDate`·`dueTime`·`reminderMinutesBefore` | **항상 null** |
| `importance`·`estimatedMinutes` | 모델 제안 — 정규화로 null이 될 수 있음 |
| `sourceExcerpt` | **항상 대상 제목** (개행을 공백으로 접고 앞뒤 공백을 없앤 `target.title`) |

### 2.4 호환성 테스트 사례

외부 OpenAI 호출 없이 fake LLM으로 검증한다.

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | 시작(질문 턴) | `201`, `sessionId == proposalId`, `items: null`, `options` 2~4개, `firstStep: null`, 비공백 `assistantText` |
| T-02 | `instruction`을 포함한 시작 | 질문 없이 바로 분해 턴 |
| T-03 | `target` 누락 / `target.title` 공백·501자 / `notes` 4001자 / `instruction` 2001자 | 각각 `422` |
| T-04 | 시작 응답의 `sessionId`로 이어가기 (`message` 하나만 전송) | `200`, 대화가 이어짐 |
| T-05 | 분해 턴 | `items` 1~5개, `options: null`, `firstStep: null`, 각 항목 `memo`·`dueDate`·`dueTime`·`reminderMinutesBefore` null, `sourceExcerpt`는 개행·앞뒤 공백을 정규화한 `target.title` |
| T-06 | 질문 턴 5회 도달 후 이어가기 | 응답은 반드시 분해 턴 |
| T-07 | 분해 턴 후 같은 세션에 "더 잘게 쪼개줘" | 직전 목록 기반 재분해, `items` ≤ 5개 |
| T-08 | 쪼개기 시작 기록이 없는 세션에 이어가기 | `404` |
| T-09 | `message` 공백·2001자 | `422` |
| T-10 | 분해 턴에서 `items`가 빈 모델 응답 | `503` |
