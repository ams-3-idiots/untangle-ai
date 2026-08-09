# 01. 에이전트 구축 전 대화형 AI 최소 기능 구현

## 1. 목적

Streamlit 데모 `../untangle-ai-demo`의 브레인덤프와 할 일 쪼개기를 FastAPI로
옮긴다. 이 구현은 독립적인 완성형 AI 계층이 아니라, 바로 다음 작업에서 생산성 앱
전용 에이전트가 호출할 수 있는 최소 생성 기능을 확보하는 데 목적이 있다.

단발 생성만 제공하면 입력이 모호할 때 빈 결과나 낮은 품질의 후보를 바로 반환할
수 있다. 따라서 각 기능 API는 필요한 정보가 부족할 때 질문 하나를 반환하고,
앱이 답변을 추가해 같은 API를 다시 호출하는 최소 구체화 대화를 포함한다.

이번 이슈에서 핵심 규칙은 다음과 같다.

- 질문 또는 완료 결과를 구분하는 엄격한 DTO
- 원본 입력과 누적 답변만으로 동작하는 무상태 feature service
- 최대 질문 수와 최대 후보 수 같은 결정적 업무 규칙

LLM provider 연결, prompt 구성, 호출 방식은 후속 에이전트 아키텍처에서 변경될 수
있다. 이번 단계에서 해당 부분을 범용화하지 않는다.

## 2. 핵심 결정

### 2.1 두 개의 대화형 API만 만든다

- `POST /api/v1/ai/brain-dump`
- `POST /api/v1/ai/task-breakdown`

별도의 `/clarify` 엔드포인트를 만들지 않는다. 각 API는 현재 입력과 이전 구체화
답변을 받아 다음 둘 중 하나를 반환한다.

- `needs_clarification`: 정보가 부족해 질문 하나가 필요함
- `completed`: 정보가 충분하거나 질문 한도에 도달해 결과를 반환함

### 2.2 기능 안의 최소 구체화만 포함한다

이번 이슈에는 후보 생성에 직접 필요한 구체화만 포함한다.

- 한 번의 응답에는 질문 하나만 반환한다.
- 이미 답했거나 건너뛴 질문을 다시 묻지 않는다.
- 브레인덤프는 최대 1회, 할 일 쪼개기는 최대 3회 질문한다.
- 질문 한도에 도달하면 현재 정보로 결과를 생성한다.
- 사용자는 질문을 건너뛰고 현재 정보로 결과 생성을 진행할 수 있다.

자유 대화, 여러 기능 간 의도 전환, 장기 기억, 도구 선택은 후속 Agent Runner의
책임이다. 공식 OpenAI 문서도 에이전트 구성에서 conversation state, 실행,
orchestration, guardrail을 별도 개념으로 다룬다. 기능 내부의 제한된 구체화만 먼저
구현하고 일반 orchestration을 후속으로 두는 것은 이 프로젝트의 설계 판단이다.
[OpenAI Agents 문서](https://developers.openai.com/api/docs/guides/agents)를 참고한다.

### 2.3 서버는 대화 상태를 저장하지 않는다

앱은 원본 입력과 서버가 반환한 질문, 사용자의 답변 또는 건너뛰기 여부를 보관한다.
다음 요청에서 이 구조화된 이력을 다시 보내며 서버는 모든 요청을 독립적으로
처리한다.

서버는 다음 항목을 만들지 않는다.

- conversation·session ID
- 메모리 또는 DB 기반 대화 상태
- 사용자별 진행 단계
- provider의 대화 객체를 그대로 노출하는 계약

### 2.4 하나의 provider만 연결한다

구현 직전에 첫 에이전트에서도 사용할 LLM provider 하나를 정하고 해당 SDK만
추가한다. 이번 이슈에서는 다음을 만들지 않는다.

- OpenAI·Anthropic 동시 지원
- `LLM_PROVIDER`에 따른 자동 선택
- 키 존재 여부에 따른 provider 우선순위
- provider fallback과 자동 재시도
- provider별 호환 처리
- 범용 `ModelPort` 또는 adapter 계층

기능 service가 SDK 객체를 직접 다루지 않도록 한 개의 얇은 LLM 호출 함수만 둔다.

### 2.5 모델 출력 DTO와 API 응답 DTO를 구분한다

선택한 provider의 structured output 또는 JSON schema 기능을 우선 사용한다.

- 모델 출력 형식은 `app/schemas/`의 Pydantic DTO로 정의한다.
- LLM 호출 함수는 provider 원본 응답을 모델 출력 DTO로 검증해 반환한다.
- SDK 객체와 raw 문자열을 feature service에 노출하지 않는다.
- feature service는 질문 이력 규칙과 결과 정규화를 적용해 API 응답 DTO로 변환한다.
- DTO 검증에 실패하면 `InvalidAIResponseError`를 발생시킨다.

권장 이름은 다음과 같다.

- `BrainDumpModelOutput`, `TaskBreakdownModelOutput`
- `BrainDumpResponse`, `TaskBreakdownResponse`
- `ClarificationQuestion`, `ClarificationAnswer`

모델 출력과 API 응답은 `status`를 discriminator로 사용하는 union DTO로 정의한다.
정식 schema와 다르면 복구하지 않고 `invalid_ai_response`로 처리한다.

## 3. 범위

### 3.1 포함

- 브레인덤프 대화형 API 한 개
- 할 일 쪼개기 대화형 API 한 개
- 원본 입력과 구조화된 구체화 이력을 받는 요청 DTO
- `needs_clarification`과 `completed` 응답 DTO
- 질문 하나 반환, 질문 중복 방지, 건너뛰기, 최대 질문 수
- `title`, `memo` 중심의 후보 DTO
- `trim + casefold` 기준 제목 중복 제거, 순서 유지, 최대 5개 제한
- 단일 LLM provider의 SDK 호출
- 설정 누락, 외부 호출 실패, 잘못된 모델 응답의 도메인 오류 변환
- 외부 LLM을 fake로 바꾼 최소 계약 테스트
- `.env.example`의 단일 provider 설정 예시

### 3.2 제외

- 별도의 범용 채팅 함수나 api 엔드포인트
- 서버에 저장하는 conversation·session state
- Co-Planner 자유 대화와 기능 간 의도 분류
- agent loop, tool registry, run state, memory, trace
- provider 추상화, 복수 provider, fallback, 자동 재시도
- 잘못된 모델 응답 형식을 되살리려는 방어적·legacy 파싱
- prompt/model 평가 데이터셋과 평가 실행기
- AI 결과 선택·확정·보관
- Todo 생성·수정·삭제·완료·재정렬·저장
- DB model, repository, migration, transaction
- 인증, 권한, 사용량 제한, 비용 제어

인증이 후속 범위인 동안 두 API는 내부 개발 환경에서만 사용하고 외부에 공개하지
않는다. 개인정보 정책이 정해지기 전에는 브레인덤프·목표·답변과 모델 원문 응답을
로그에 남기지 않는다. 이는 새 기능이 아니라 임시 API의 공개 제한이다.

## 4. 최소 구조와 흐름

```text
원본 입력 + clarification 이력
  → endpoint
  → feature service
      → 단일 provider용 얇은 llm_service
      → 모델 출력 union DTO 검증
      ├─ needs_clarification: 물어도 되는 질문인지 확인한다
      └─ completed: 후보 목록을 규칙대로 정리한다
  → API 응답 union DTO
```

모델이 질문을 반환하면 질문 내용은 고치지 않고 물어도 되는 질문인지만 확인한다.
기능이 허용하지 않은 항목을 묻거나, 사용자가 이미 답하거나 건너뛴 항목을 다시
묻거나, 질문 한도를 넘겨 묻는다면 `invalid_ai_response`로 처리한다.

모델이 결과를 반환하면 후보 목록을 그대로 쓰지 않고 정해진 규칙으로 정리한다.
제목의 앞뒤 공백을 없애고, 공백과 대소문자를 무시했을 때 같은 제목은 하나만
남기며, 모델이 준 순서를 유지한 채 최대 5개까지만 반환한다.

두 기능은 DB를 사용하지 않는다. `models`, `repositories`, `db`를 참조하지 않고
기존 의존 방향인 `api → services → schemas/exceptions`를 지킨다.

```text
최초 요청
  → 정보 부족: needs_clarification + 질문 하나
  → 앱이 답변 또는 skip을 clarification 이력에 추가
  → 같은 API 재요청
  → 정보 충분 또는 질문 한도 도달: completed + 최종 결과
```

엔드포인트는 동기 `def`로 선언하고 `response_model`과 union DTO 반환형을 명시한다.
에이전트 단계에서는 HTTP를 다시 호출하지 않고 두 feature service를 R1 후보 생성
tool handler가 감쌀 수 있게 한다.

| 구분 | 내용 |
| --- | --- |
| 유지할 발판 | 요청·응답 DTO, 무상태 service, 질문·후보 상한 |
| 교체 가능 | 정보 충분성 prompt, LLM SDK 호출, model 설정 |
| 후속 추가 | Agent Runner, 기능 간 orchestration, ModelPort, trace·평가 |

## 5. 공통 DTO 계약

### 5.1 후보 DTO

```json
{
  "title": "치과 예약하기",
  "memo": "이번 주 안에"
}
```

- `title`은 trim 후 비어 있을 수 없다.
- `memo`는 선택 정보이며 없으면 빈 문자열을 사용한다.
- ID, 완료 여부, 우선순위, 생성 시각 등 저장 필드는 포함하지 않는다.
- UI 안내 문구는 응답 DTO에 넣지 않는다.

### 5.2 구체화 질문 DTO

```json
{
  "key": "capacity",
  "text": "하루에 이 일에 사용할 수 있는 시간은 얼마나 되나요?",
  "options": ["10분", "30분", "1시간 이상"]
}
```

- `key`는 기능별 허용값 중 하나다.
- `text`는 한 번에 하나의 정보만 묻는다.
- `options`는 생략 가능하며 제공하면 2~4개로 제한한다.
- 앱은 선택지와 별개로 자유 입력을 항상 제공할 수 있다.

### 5.3 누적 답변 DTO

답한 질문:

```json
{
  "key": "capacity",
  "text": "하루에 이 일에 사용할 수 있는 시간은 얼마나 되나요?",
  "answer": "평일 저녁 30분",
  "skipped": false
}
```

건너뛴 질문:

```json
{
  "key": "blocker",
  "text": "이 일을 시작하기 어렵게 만드는 것은 무엇인가요?",
  "answer": null,
  "skipped": true
}
```

- `skipped=false`이면 trim 후 비어 있지 않은 `answer`가 필요하다.
- `skipped=true`이면 `answer=null`이어야 한다.
- 앱은 서버가 반환한 `key`와 `text`를 바꾸지 않고 다음 요청에 전달한다.
- 같은 `key`는 이력에 한 번만 존재할 수 있다.

### 5.4 공통 응답 형태

질문이 필요한 경우:

```json
{
  "status": "needs_clarification",
  "question": {
    "key": "capacity",
    "text": "하루에 이 일에 사용할 수 있는 시간은 얼마나 되나요?",
    "options": ["10분", "30분", "1시간 이상"]
  }
}
```

완료된 경우:

```json
{
  "status": "completed",
  "result": {}
}
```

`needs_clarification`에는 `question`만, `completed`에는 기능별 `result`만 존재해야
한다. 두 필드가 동시에 있거나 모두 없으면 모델 응답 오류다.

## 6. 브레인덤프 API

`POST /api/v1/ai/brain-dump`

### 6.1 요청

```json
{
  "text": "요즘 일이 너무 복잡해서 뭘 해야 할지 모르겠어.",
  "clarifications": []
}
```

`clarifications`는 생략할 수 있으며 기본값은 빈 목록이다.

### 6.2 정보가 부족한 응답

```json
{
  "status": "needs_clarification",
  "question": {
    "key": "action_detail",
    "text": "지금 마음에 걸리는 일 중 직접 해야 하는 일을 한 가지만 말해줄래요?",
    "options": []
  }
}
```

답변 후 재요청:

```json
{
  "text": "요즘 일이 너무 복잡해서 뭘 해야 할지 모르겠어.",
  "clarifications": [
    {
      "key": "action_detail",
      "text": "지금 마음에 걸리는 일 중 직접 해야 하는 일을 한 가지만 말해줄래요?",
      "answer": "다음 주 발표 자료를 준비해야 해.",
      "skipped": false
    }
  ]
}
```

### 6.3 완료 응답

```json
{
  "status": "completed",
  "result": {
    "candidates": [
      {
        "title": "다음 주 발표 자료 준비하기",
        "memo": ""
      }
    ]
  }
}
```

정상 빈 결과:

```json
{
  "status": "completed",
  "result": {
    "candidates": []
  }
}
```

### 6.4 업무 규칙

- 입력에서 근거 있는 후보가 하나라도 나오면 추가 질문 없이 `completed`를 반환한다.
- 후보가 하나도 없고 해결되지 않은 고민이 드러나면 `action_detail`을 한 번 묻는다.
- 질문에 답하거나 건너뛰면 더 묻지 않고 현재 정보로 결과를 생성한다.
- 감정·상태·바람을 새로운 행동으로 바꾸지 않는다.
- 입력에 명시된 큰 목표를 임의로 쪼개지 않는다.
- title의 `trim + casefold` 결과가 같으면 첫 후보만 유지한다.
- 입력 순서를 유지하며 최대 5개를 반환한다.
- 데모 prompt의 행동 추출 규칙은 유지하되 질문·완료 union DTO에 맞게 출력 지시를
  변경한다. 이 이슈에서 품질 튜닝은 하지 않는다.

## 7. 할 일 쪼개기 API

`POST /api/v1/ai/task-breakdown`

### 7.1 요청

```json
{
  "goal": "이직용 포트폴리오 만들기",
  "clarifications": []
}
```

### 7.2 정보가 부족한 응답

```json
{
  "status": "needs_clarification",
  "question": {
    "key": "progress",
    "text": "포트폴리오 준비는 지금 어디까지 되어 있나요?",
    "options": ["아직 시작하지 않았어요", "프로젝트 후보만 정했어요", "초안이 있어요"]
  }
}
```

누적 답변을 포함한 재요청:

```json
{
  "goal": "이직용 포트폴리오 만들기",
  "clarifications": [
    {
      "key": "progress",
      "text": "포트폴리오 준비는 지금 어디까지 되어 있나요?",
      "answer": "프로젝트 후보 2개를 정했어요.",
      "skipped": false
    },
    {
      "key": "capacity",
      "text": "하루에 이 일에 사용할 수 있는 시간은 얼마나 되나요?",
      "answer": "평일 저녁 30분",
      "skipped": false
    }
  ]
}
```

### 7.3 완료 응답

```json
{
  "status": "completed",
  "result": {
    "first_step": {
      "title": "새 포트폴리오 문서 파일 열기",
      "memo": ""
    },
    "steps": [
      {
        "title": "첫 번째 프로젝트의 문제와 해결 방법 적기",
        "memo": "30분 안에 초안만 작성"
      },
      {
        "title": "두 번째 프로젝트의 문제와 해결 방법 적기",
        "memo": ""
      }
    ]
  }
}
```

정상 빈 결과:

```json
{
  "status": "completed",
  "result": {
    "first_step": null,
    "steps": []
  }
}
```

### 7.4 업무 규칙

- `progress`, `done`, `capacity`, `blocker` 중 결과를 가장 크게 바꿀 질문만 고른다.
- 목표와 이전 답변에 이미 있는 내용은 다시 묻지 않는다.
- 한 요청에서는 질문 하나만 반환하고 최대 3회까지 질문한다.
- 모든 dimension을 채우는 설문으로 만들지 않는다.
- 사용자가 질문을 건너뛰면 해당 `key`를 다시 묻지 않는다.
- 정보가 충분하거나 질문 3회에 도달하면 현재 정보로 결과를 생성한다.
- `first_step`은 목표에 특화되고 바로 착수할 수 있는 가장 작은 행동으로 만든다.
- `steps`는 실행 순서를 유지한다.
- `first_step`과 `steps`를 합쳐 최대 5개를 반환한다.
- 전체 결과에서 title의 `trim + casefold`가 같으면 `first_step`을 우선 유지하고
  중복된 후속 단계를 제거한다.
- 결과가 비어 있지 않으면 유효한 `first_step`이 반드시 있어야 한다.
- `first_step=null`인데 `steps`가 있으면 승격하지 않고 모델 응답 오류로 처리한다.
- 데모 prompt의 분해 규칙은 유지하되 질문·완료 union DTO에 맞게 출력 지시를
  변경한다. 이 이슈에서 품질 튜닝은 하지 않는다.

## 8. 입력과 상태 검증

### 8.1 길이와 개수

- `text`: trim 후 1~10,000자
- `goal`: trim 후 1~2,000자
- 질문 `text`: trim 후 1~500자
- 답변 `answer`: 전달하면 trim 후 1~1,000자
- 질문 선택지: 0개 또는 2~4개, 항목당 1~200자
- 브레인덤프 clarification 이력: 최대 1개
- 할 일 쪼개기 clarification 이력: 최대 3개

### 8.2 이력 검증

- 기능별 허용 `key`만 받는다.
- 같은 `key`가 두 번 있으면 `422`로 거절한다.
- `answer`와 `skipped` 조합이 맞지 않으면 `422`로 거절한다.
- 최대 이력 수를 넘으면 `422`로 거절한다.
- 요청 형식 오류는 LLM 호출 전에 차단한다.
- 이미 답했거나 건너뛴 `key`를 모델이 다시 질문하면 `invalid_ai_response`로 처리한다.
- 질문 한도에서 모델이 다시 질문하면 `invalid_ai_response`로 처리한다.

중복 key와 질문 한도는 업무 규칙이므로 feature service에서 검증하고
`InvalidClarificationStateError`를 발생시킨다. 필드 타입·길이·answer 조합은
schema에서 검증한다.

## 9. LLM 호출과 오류

### 9.1 단일 provider 설정

구현 전에 실제 에이전트 PoC에서 사용할 provider 하나를 고른다. 선택한 provider의
API key, model, timeout만 `app/core/config.py`와 `.env.example`에 추가하고 해당
SDK 하나만 `pyproject.toml`에 설치한다.

- `LLM_PROVIDER`와 자동 선택 로직은 추가하지 않는다.
- API key는 앱 시작의 필수값으로 만들지 않고 AI 호출 시점에 검사한다.
- 키가 없어도 health API와 서버는 기동되어야 한다.
- timeout은 명시하되 app 수준 retry와 provider fallback은 구현하지 않는다.
- LLM 호출 함수는 요청마다 기능별 model output DTO를 response schema로 받는다.

### 9.2 모델 응답 처리

모델은 한 번의 호출에서 질문 또는 완료 결과 중 하나를 반환한다.

브레인덤프 질문 형식:

```json
{
  "status": "needs_clarification",
  "question": {
    "key": "action_detail",
    "text": "직접 해야 하는 일을 한 가지만 말해줄래요?",
    "options": []
  }
}
```

브레인덤프 완료 형식:

```json
{
  "status": "completed",
  "result": {
    "candidates": []
  }
}
```

할 일 쪼개기도 같은 discriminator를 사용하고 `completed.result`만
`first_step`, `steps` DTO로 바꾼다.

정식 schema 검증 후 질문 이력 규칙 또는 title trim, `casefold` 중복 제거, 최대
5개 제한만 적용한다. 코드 펜스, wrapper 별칭, legacy 배열은 복구하지 않는다.

### 9.3 오류 계약

서비스는 `HTTPException` 대신 `app/exceptions/ai.py`의 `DomainError` 하위 예외를
발생시킨다. 기존 전역 handler가 다음 형식으로 변환한다.

```json
{
  "code": "ai_provider_error",
  "message": "AI 응답을 가져오지 못했습니다. 잠시 후 다시 시도해주세요."
}
```

| 상황 | 상태 | 오류 코드 |
| --- | ---: | --- |
| 필드 타입·공백·길이·answer 조합 오류 | `422` | FastAPI 검증 오류 |
| 중복 key·질문 한도 초과 요청 | `422` | `invalid_clarification_state` |
| provider key·model 설정 누락 | `503` | `ai_not_configured` |
| timeout·네트워크·SDK 호출 실패 | `502` | `ai_provider_error` |
| union DTO·질문 이력 규칙을 어긴 모델 응답 | `502` | `invalid_ai_response` |
| 정식 빈 후보·빈 분해 결과 | `200` | 없음 |

사용자 정보 부족과 질문 반환은 오류가 아니며 `200 needs_clarification`로 처리한다.
SDK 예외명, API key, 모델 원문 응답은 HTTP 응답에 노출하지 않는다.