# 02. API 테스트를 위한 Swagger 설정

## 0. 목차

1. [목적](#1-목적) — 자동 생성 문서를 다듬는 이유와 목표
2. [핵심 결정](#2-핵심-결정) — 문서를 항상 켜 두는 이유, 메타데이터가 붙는 레이어
3. [범위](#3-범위) — 이번 이슈에 포함하는 것과 제외하는 것
4. [상세 설계](#4-상세-설계) — 앱·엔드포인트·스키마 메타데이터, 오류 응답, 직접 호출
5. [완료 조건](#5-완료-조건) — 이슈를 닫기 전에 확인하는 항목

## 1. 목적

AI API를 앱 개발자와 공유하려면 요청·응답 형식을 사람이 읽을 수 있는 형태로
제공해야 한다.
FastAPI는 이미 코드에서 OpenAPI 문서를 만들어 주므로 명세 문서를 따로 손으로
유지하지 않는다. 이번 이슈는 api 문서 생성을 통해 두 가지를 만족하기 위해 진행하는 작업이다.

- API 명세: 엔드포인트·스키마에 설명과 예시를 붙인다
- api 호출 가능: Swagger UI에서 바로 요청을 보낼 수 있게 한다

## 2. 핵심 결정

### 2.1 문서는 항상 켜 둔다

이번 이슈의 목적이 팀원과의 명세 공유이므로 `/docs`, `/redoc`, `/openapi.json`을
끄는 설정을 두지 않는다.

### 2.2 문서용 메타데이터는 기존 레이어 안에 붙인다

문서를 위해 새 레이어를 만들지 않는다. 엔드포인트와 스키마의 설명은 각 레이어
안에 함께 두고, 앱 수준 메타데이터만 `main.py`에서 조립한다.

새로 만드는 파일은 `app/core/openapi.py` 하나다. Swagger 첫 화면에 보이는 앱 설명과
태그 목록을 상수로 모아 둔다. 환경에 따라 달라지는 값을 읽는 `config.py`와 달리
문서에 그대로 노출되는 고정 문자열이라 따로 둔다.

## 3. 범위

### 3.1 포함

- 앱 제목·설명·태그 목록 지정
- 태그별 설명과 엔드포인트 `summary`·docstring 정리
- 요청·응답 스키마의 필드 설명과 예시
- 공통 오류 응답 스키마와 엔드포인트 `responses` 선언
- FastAPI 검증 오류와 코드가 겹치는 도메인 예외의 상태 코드 변경(`422` → `400`)

### 3.2 제외

- Swagger UI 테마·정적 파일 자체 호스팅
- 명세 파일을 저장소에 커밋해 관리하는 방식

## 4. 상세 설계

문서에 들어갈 내용은 코드 곳곳에 나뉘어 붙는다. 문서에서 차지하는 범위가 넓은
것부터 좁은 것 순으로, 붙는 위치를 따라간다.

- `main.py`와 `core/openapi.py` — 문서 첫 화면의 제목·설명과 태그 목록
- 엔드포인트 — 목록에 보이는 한 줄과 펼쳤을 때의 설명
- 스키마 — 요청·응답 본문의 필드 설명과 `Try it out`에 채워질 예시

오류 응답은 FastAPI가 자동으로 문서화하지 못하므로 따로 다루고, 마지막에 Swagger
UI에서 직접 호출해 확인하는 방법을 둔다.

### 4.1 앱 메타데이터와 태그

`app/main.py`에서 앱 수준 메타데이터를 조립한다.

```python
app = FastAPI(
    title=settings.app_name,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
)
```

- `docs_url`, `redoc_url`, `openapi_url`은 지정하지 않는다. FastAPI 기본값이 아래
  세 경로를 그대로 연다.

| 경로 | 내용 |
| --- | --- |
| `/docs` | Swagger UI. 요청을 직접 보내 볼 수 있다 |
| `/redoc` | ReDoc. 읽기 전용이며 긴 설명을 보기 좋다 |
| `/openapi.json` | OpenAPI 명세 원본. 공유·도구 연동의 기준 |

`app/core/openapi.py`를 새로 만들고 두 상수를 둔다.

```python
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
```

- 태그 이름은 라우터의 `APIRouter(prefix="/ai", tags=["ai"])` 선언과 같아야 한다.
- 태그는 도메인 단위로만 만든다. 엔드포인트마다 새 태그를 만들지 않는다.
- `OPENAPI_TAGS`의 순서가 Swagger UI에 표시되는 순서가 된다.

### 4.2 엔드포인트 메타데이터

엔드포인트 선언에 문서용 정보를 함께 적는다.

```python
@router.post(
    "/brain-dump",
    response_model=BrainDumpResponse,
    summary="브레인덤프에서 할 일 후보를 뽑는다",
    responses=AI_ERROR_RESPONSES,
)
def create_brain_dump(payload: BrainDumpRequest) -> BrainDumpResponse:
    """정보가 부족하면 질문 하나를, 충분하면 후보 목록을 반환한다.

    앱은 서버가 준 질문과 답변을 `clarifications`에 누적해 다시 호출한다.
    """
    return brain_dump_service.create_brain_dump(payload)
```

- `summary`는 목록에 보이는 한 줄이다. 동사로 끝나는 짧은 문장으로 쓴다.
- **함수 docstring이 그대로 Swagger 설명이 된다.** 내부 구현이 아니라 호출하는
  쪽이 알아야 할 규칙을 쓴다.
- `response_model`을 생략하면 응답 스키마가 문서에 나오지 않으므로 반드시 적는다.
- 성공 상태 코드가 200이 아니면 `status_code`도 함께 적는다.

### 4.3 스키마 설명과 예시

필드 설명은 `Field`에, 요청 전체 예시는 `model_config`에 둔다.

```python
class BrainDumpRequest(BaseModel):
    """브레인덤프 생성 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"text": "요즘 일이 너무 복잡해서 뭘 해야 할지 모르겠어."}]
        }
    )

    text: str = Field(min_length=1, max_length=10_000, description="정리되지 않은 생각")
    clarifications: list[ClarificationAnswer] = Field(
        default_factory=list,
        max_length=1,
        description="이전 응답의 질문과 사용자의 답변 이력",
    )
```

- 예시는 Swagger UI의 `Try it out` 입력창에 그대로 채워지므로, 복사해서 바로 보낼
  수 있는 값으로 쓴다.
- `Field`의 제약(`min_length`, `max_length`)은 문서의 스키마 설명에도 반영된다. 설명 문구로 다시 반복하지 않는다.
- [01번 이슈](01-ai-api.md#54-공통-응답-형태)의 `status` discriminator union 응답은
  Swagger UI에서 두 개의 선택지로 표시된다. 각 하위 DTO에 예시를 하나씩 둬야 두 경우가 모두 보인다.

### 4.4 오류 응답 문서화

- `DomainError`는 핸들러에서 JSON으로 바뀌므로 FastAPI가 자동으로 문서화하지 못한다.
- 응답 본문 형식을 `app/schemas/error.py`에 정의한다.

```python
class ErrorResponse(BaseModel):
    """`exceptions/handlers.py`가 반환하는 공통 오류 본문."""

    code: str = Field(description="오류 종류를 구분하는 코드")
    message: str = Field(description="사용자에게 보여줄 수 있는 설명")
```

- `DomainError`에 API 사용자에게 보여줄 설명인 `description` 속성을 추가하고 하위 클래스에서 `status_code`·`code`와 나란히 재정의한다.

```python
class DomainError(Exception):
    """업무 규칙 위반을 나타내는 예외.

    하위 클래스는 `status_code`·`code`·`description`을 재정의해
    어떤 HTTP 응답과 문서 설명으로 바뀔지 정한다.
    """

    status_code: int = 400
    code: str = "domain_error"
    description: str = "도메인 규칙 위반으로 요청을 처리할 수 없다."
```

하위 클래스는 자신의 오류 상황에 맞는 문구로 재정의한다.

```python
class AIProviderError(DomainError):
    """timeout·네트워크 등으로 OpenAI 호출 자체가 실패한 상태."""

    status_code = 502
    code = "ai_provider_error"
    description = "LLM 호출이 실패했다."
```

- docstring은 코드를 읽는 개발자용, `description`은 문서에 노출되는 소비자용으로
  분리한다. docstring을 다듬어도 공개 명세는 바뀌지 않는다.

예외 클래스의 `status_code`와 `description`을 읽어 `responses` 선언을 만드는
변환 함수를 `exceptions/handlers.py`에 둔다. 런타임 변환(핸들러)과 문서화 변환이
같은 파일에서 관리된다.

```python
def error_responses(*errors: type[DomainError]) -> dict[int, dict[str, Any]]:
    """도메인 예외 목록을 문서화하기 위해 엔드포인트 `responses` 선언으로 변환한다."""
    grouped: dict[int, list[str]] = {}
    for error in errors:
        grouped.setdefault(error.status_code, []).append(error.description)
    return {
        status: {"model": ErrorResponse, "description": "\n\n".join(docs)}
        for status, docs in grouped.items()
    }
```

- 도메인 예외에는 `422`를 쓰지 않는다(AGENTS.md 1.3). FastAPI가 요청 형식
  오류(Pydantic 검증 실패)를 자동 문서화할 때 쓰는 코드와 겹쳐, 선언이 그 문서를
  덮어쓰고 변환 함수에 특례가 필요해지기 때문이다.
- 이에 따라 `InvalidClarificationStateError`의 `status_code`를 `400`으로 바꾸고,
  이 오류의 상태 코드를 확인하는 테스트도 함께 수정한다.

역할은 둘로 나뉜다. 상태 코드·설명은 예외 클래스에서 오고, **어떤 예외를 낼 수
있는지는 엔드포인트가 고른다.** 엔드포인트는 자신이 발생시킬 수 있는 예외만
`error_responses()`에 넘긴다. 예를 들어 두 예외만 내는 엔드포인트라면 그 둘만
선언한다.

```python
responses = error_responses(InvalidClarificationStateError, AIProviderError)
```

### 4.5 Swagger UI에서 직접 호출

개발 서버를 띄우고 브라우저에서 확인한다.

```bash
uv run fastapi dev app/main.py
```

- `http://127.0.0.1:8000/docs`에서 엔드포인트를 펼치고 `Try it out`을 누른다.
- 요청 본문에는 4.3의 예시가 채워져 있으므로 값만 바꿔 `Execute`한다.
- 응답 코드, 응답 본문, 실제 요청 `curl` 명령을 함께 확인할 수 있다.

## 5. 완료 조건

- `uv run fastapi dev app/main.py` 실행 후 `/docs`, `/redoc`, `/openapi.json`이 열린다.
- 모든 엔드포인트에 `summary`, docstring, `response_model`이 있다.
- 모든 태그에 설명이 있고 태그 없는 엔드포인트가 없다.
- 도메인 오류를 반환할 수 있는 엔드포인트에 `responses`가 선언되어 있다.
- `422`를 상태 코드로 쓰는 도메인 예외가 없다.
- 요청 DTO의 예시를 Swagger UI에서 그대로 보내면 정상 응답을 받는다.
