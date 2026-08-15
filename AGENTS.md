# 에이전트 지침

## 답변 방식
  - 모든 답변은 결론, 결과 또는 권장안처럼 사용자에게 가장 중요한 내용부터 제시한다.
  - 답변의 첫 부분은 핵심을 빠르게 파악할 수 있도록 간결하게 작성한다.
  - 제안·비교·검토에서는 권장안과 핵심 판단 근거를 먼저 제시한 뒤 세부 사항을 중요도순으로 설명한다.
  - 업무 진행 상황이나 결과를 보고할 때는 현재 상태 또는 성과를 먼저 제시하고, 수행한 내용과 남은 사항을 중요도순으로 설명한다.

# 개발 가이드라인

## 0. 문서 구성

### 0.1 개발 가이드라인의 상시 규칙

1. [프로젝트 구조](#1-프로젝트-구조) — 레이어 역할과 의존 방향, 이름 규칙, OpenAPI 문서화
2. [Python 코드 스타일](#2-python-코드-스타일) — Docstring과 주석, Ruff 실행과 검증 기준
3. [작업 완료 전 확인](#3-작업-완료-전-확인) — 테스트 실행 시점과 실패 처리, API 문서 확인
4. [커밋 전 사용자 검토](#4-커밋-전-사용자-검토) — 커밋 생성 전 승인 절차

### 0.2 상황별로 읽는 규약 문서

특정 시점에만 필요한 절차 지침은 `docs/conventions/`에 두고 그 시점에 읽는다.
아래 상황에서는 **작업을 시작하기 전에 해당 문서를 읽고 그대로 따른다.**

| 상황 | 문서 |
| --- | --- |
| 테스트를 작성·수정하거나 테스트 구조를 정할 때 | [`docs/conventions/testing.md`](docs/conventions/testing.md) |
| 브랜치를 만들 때, 커밋할 때, PR을 올릴 때 | [`docs/conventions/git.md`](docs/conventions/git.md) |
| GitHub 이슈를 작성·수정하거나 이슈에 연결할 스펙 문서를 쓸 때 | [`docs/conventions/git.md`](docs/conventions/git.md) |

## 1. 프로젝트 구조

### 1.1 레이어와 역할

| 디렉토리 | 역할 |
| --- | --- |
| `app/main.py` | 앱 시작점 |
| `app/api/` | HTTP 엔드포인트 |
| `app/services/` | 비즈니스 로직 |
| `app/schemas/` | 요청·응답 형식 |
| `app/exceptions/` | 도메인 예외와 HTTP 오류 변환 |
| `app/core/` | 환경 설정과 문서용 고정 문자열 |
| `tests/` | API와 비즈니스 로직 테스트 |

영구 저장소를 쓰지 않는 서버라 DB 레이어(`models`·`repositories`·`db`)를 두지 않는다.
요청 사이에 유지해야 하는 상태는 `services`가 프로세스 안에서 직접 관리한다.

### 1.2 의존 방향

```
main → api → services

schemas : api, services 가 참조하며, exceptions 도 공통 오류 본문(ProblemDetail)을 참조
exceptions : 도메인 예외와 HTTP 응답 변환을 관리한다.
             services는 도메인 예외를 참조하고, main은 예외 핸들러를 등록하며,
             api는 responses 문서화를 위해 도메인 예외와 error_responses 를 참조한다.
core    : 환경 설정(config)과 문서용 고정 문자열(openapi)을 제공.
          main·services 가 참조하며, core 는 다른 레이어를 참조하지 않는다.
```
- **의존 방향이 어긋나는 코드는 절대 작성하지 않습니다.**

### 1.3 데이터 흐름과 책임

```
요청 → endpoint  : schemas 로 형식 검증
     → service   : 업무 규칙 판단, 상태 보관과 외부 호출
응답 ← endpoint  : services가 반환한 schemas DTO를 response_model로 직렬화
```

- **데이터 검증**: 타입·필수값·형식은 `schemas`, 비즈니스 로직 관련 검증(중복 이메일, 권한 등)은 `services`.
- **예외 처리**: `services`는 `exceptions`에 정의된 도메인 예외를 발생시키며 `HTTPException`을 사용하지 않는다. 도메인 예외를 HTTP 상태 코드와 응답 본문으로 변환하는 처리도 `exceptions`에서 관리하고, `main.py`는 예외 핸들러를 애플리케이션에 등록한다.
- **도메인 예외 상태 코드**: 도메인 예외에는 `422`를 사용하지 않는다. `422`는 `schemas`에서 처리하는 요청 형식의 Pydantic 검증 실패에만 사용하며, 본문은 전역 핸들러가 ProblemDetail로 변환한다. 업무 규칙 위반에는 의미에 맞는 다른 상태 코드(`400`, `404`, `409` 등)를 선택한다.
- **상태 보관**: 요청 사이에 유지할 상태는 전용 `services` 모듈 하나가 프로세스 안에서
  들고 있고, 다른 레이어는 그 모듈을 통해서만 읽고 쓴다.
  상태는 재시작·배포로 사라지므로 사라졌을 때의 응답까지 정하고 쓴다.
  보관량 상한과 보관 시간은 설정에서 읽고 서비스에 하드코딩하지 않는다.
  `api/dependencies.py`에는 요청 단위 의존성(현재 사용자, 페이지네이션 등)만 둔다.
- **응답 DTO**: `services`는 내부 자료구조를 `schemas`에 정의된 응답 DTO로 변환한다.
  엔드포인트는 서비스 내부 타입을 직접 참조하지 않고 `services`가 반환한 DTO만 반환한다.
- **엔드포인트 선언**: 서비스가 동기로 동작하므로 엔드포인트는 `def`로 선언한다.

`services/ai_session_service.py`:

```python
"""AI 세션 생성과 브레인덤프의 유스케이스."""


def create_session() -> SessionCreatedResponse:
    """새 대화 세션을 만들어 앱이 이어서 쓸 세션 식별자를 반환한다."""
    session = session_service.create_session()
    return SessionCreatedResponse(session_id=session.session_id)
```

`api/v1/endpoints/ai_session.py`:

```python
"""AI 세션 API 엔드포인트를 제공한다."""


@router.post("", response_model=SessionCreatedResponse, status_code=201)
def create_ai_session() -> SessionCreatedResponse:
    """본문 없이 호출하며, 받은 `sessionId`를 이후 요청 경로에 싣는다."""
    return ai_session_service.create_session()
```

### 1.4 파일 이름 규칙

| 위치 | 규칙 | 예 |
| --- | --- | --- |
| `api/v1/endpoints/` | 도메인 단수형 | `user.py` |
| `schemas/` | 도메인 단수형 | `user.py` |
| `services/` | `<도메인>_service.py` | `user_service.py` |

- 한 도메인은 레이어마다 같은 이름 축을 유지한다: `user` → `user.py` / `user_service.py`
- 파일이 커지면 쪼개지 말고 같은 이름의 패키지로 승격한다: `user_service.py` → `user_service/`
- API 버전이 올라가면 `api/v2/`를 새로 만들고 `v1`은 그대로 둔다.

### 1.5 새 기능 추가 순서

1. `schemas/` — 요청·응답 스키마
2. `services/` — 유스케이스와 상태 보관
3. `api/v1/endpoints/` — 엔드포인트
4. `api/v1/router.py` — 라우터 등록

로직이 거의 없어도 3번에서 2번을 건너뛰지 않는다. 기존 레이어로 설명되지 않는 코드가 생기면 새 디렉토리를 만들기 전에 사용자에게 확인한다.

### 1.6 OpenAPI/Swagger 문서화

API 명세는 손으로 쓰지 않고 FastAPI가 코드에서 생성하는 OpenAPI 문서로 공유한다.
`/docs`(Swagger UI), `/redoc`(ReDoc), `/openapi.json`(명세 원본)은 항상 열어 두며,
이 경로를 끄거나 바꾸는 설정(`docs_url` 등)을 추가하지 않는다.

문서용 메타데이터는 문서 전용 레이어를 만들지 않고 아래 위치에 나눠 붙인다.

| 위치 | 문서화 책임 |
| --- | --- |
| `main.py` | 앱 제목·설명·태그 목록을 `FastAPI(...)` 인자로 조립 |
| `core/openapi.py` | 문서에 그대로 노출되는 고정 문자열 `API_DESCRIPTION`·`OPENAPI_TAGS` |
| `api/` 엔드포인트 | `summary`·docstring·`response_model`·`status_code`·`responses` |
| `schemas/` | 필드 `description`과 요청 예시, 공통 오류 본문 `ProblemDetail` |
| `exceptions/` | 예외별 `description`, `responses` 변환(`error_responses`) |

- **태그**: 도메인 단위로만 만들고 엔드포인트마다 새 태그를 만들지 않는다.
  라우터의 `APIRouter(prefix=..., tags=[...])` 선언과 `OPENAPI_TAGS`의 이름을 일치시킨다.
  모든 태그는 `description`과 함께 `OPENAPI_TAGS`에 등록하고, 태그 없는 엔드포인트를
  두지 않는다. `OPENAPI_TAGS`의 순서가 문서에 표시되는 순서다.
- **엔드포인트**: `summary`는 목록에 보이는 한 줄이며 동사로 끝나는 짧은 문장으로 쓴다.
  함수 docstring이 그대로 Swagger 설명이 되므로 내부 구현이 아니라 호출하는 쪽이
  알아야 할 규칙을 쓰고, 길이는 [2.1](#21-docstring과-주석)의 두 줄 제한을 그대로 따른다.
- **스키마**: 필드 설명은 `Field(description=...)`에, 요청 전체 예시는 `model_config`의
  `json_schema_extra["examples"]`에 둔다. 예시는 Swagger UI의 `Try it out` 입력창에
  그대로 채워지므로 수정 없이 보내도 정상 응답을 받는 값으로 쓴다.
  `min_length` 같은 `Field` 제약은 문서에 자동 반영되므로 설명 문구로 반복하지 않는다.
  discriminated union 응답은 하위 DTO마다 예시를 하나씩 둬야 모든 경우가 문서에 보인다.
- **오류 응답**: 도메인 예외는 핸들러가 JSON으로 바꾸므로 FastAPI가 자동 문서화하지 못한다.
  `DomainError` 하위 클래스는 `status_code`·`title`과 함께 문서에 노출할
  `description`을 재정의한다. docstring은 코드를 읽는 개발자용으로 분리 유지한다.
  엔드포인트는 자신이 발생시킬 수 있는 예외만 `error_responses()`에 넘겨 `responses`로 선언한다.
- **422 도메인 예외 추가 금지**: [1.3](#13-데이터-흐름과-책임)의 규칙대로 도메인 예외에 `422`를 쓰지 않는다.
  요청 검증 실패 `422`는 전역 핸들러가 ProblemDetail로 변환하므로, 요청 본문을
  받는 엔드포인트는 `VALIDATION_ERROR_RESPONSES`를 `responses`에 합쳐
  FastAPI 기본 `422` 문서를 실제 본문 형식으로 대체한다.

[1.3](#13-데이터-흐름과-책임)의 세션 생성 엔드포인트에 문서 메타데이터를 붙이면:

```python
SESSION_ERROR_RESPONSES = error_responses(ProtectionLimitError)


@router.post(
    "",
    response_model=SessionCreatedResponse,
    status_code=201,
    summary="AI 대화 세션을 만든다",
    responses=SESSION_ERROR_RESPONSES,
)
def create_ai_session() -> SessionCreatedResponse:
    """본문 없이 호출하며, 받은 `sessionId`를 이후 요청 경로에 싣는다."""
    return ai_session_service.create_session()
```

API 변경 후 생성된 문서를 확인하는 절차는 [3. 작업 완료 전 확인](#3-작업-완료-전-확인)에 있다.

## 2. Python 코드 스타일

### 2.1 Docstring과 주석

- 직접 작성하는 Python 모듈은 파일의 책임과 존재 이유를 설명하는 모듈 docstring으로 시작한다. Docstring 본문은 두 줄 이하로 작성한다.
- 모든 클래스, 함수, 메서드의 첫 문장에는 역할이나 존재 목적을 설명하는 docstring을 작성한다. Docstring 본문은 두 줄 이하로 작성하며, **코드에서 이미 명확한 동작을 그대로 반복하지 않는다.**
- 코드 중간의 설명용 `#` 주석은 원칙적으로 작성하지 않는다.
- **코드만으로 파악하기 어려운 제약, 설계 결정, 예외 처리 또는 우회 방식의 이유를 협업자에게 알려야 할 때만 `#` 주석을 허용한다. 이때 코드가 무엇을 하는지가 아니라 왜 그렇게 작성했는지를 설명한다.**
- 자동 생성 파일과 내용이 없는 `__init__.py`는 모듈 docstring 작성 대상에서 제외한다.

### 2.2 린터 및 포매터

- Python 코드의 린터와 포매터로 Ruff를 사용한다.
- 코드 변경 후 `uv run ruff format .`으로 포맷을 적용한다.
- 작업 완료 전 `uv run ruff check .`을 실행하고 모든 린트 오류를 해결한다.
- 자동 수정이 필요한 경우 `uv run ruff check --fix .`을 실행한 뒤, `uv run ruff format .`과 `uv run ruff check .`을 다시 실행한다.
- 린트 규칙을 무시하거나 검사 대상에서 제외하는 설정은 사용자 확인 없이 추가하지 않는다.

## 3. 작업 완료 전 확인

- 기능을 수정하는 동안에는 관련 테스트를 먼저 실행하고, 작업을 마치기 전에는 전체 테스트를 실행한다.
- 실패한 테스트를 삭제하거나 건너뛰는 대신 원인을 확인해 코드 또는 테스트를 수정한다.
- API 엔드포인트나 스키마를 변경했다면 생성된 문서를 직접 확인한다.
  - OpenAPI 명세가 오류 없이 생성되는지 확인한다.

    ```bash
    uv run python -c "from app.main import app; app.openapi()"
    ```

  - 요청 예시가 실행 가능한지 확인한다. `uv run fastapi dev app/main.py`로 서버를 띄우고
    `/docs`에서 변경한 엔드포인트의 `Try it out`에 채워진 예시를 그대로 `Execute`하거나,
    브라우저를 쓸 수 없으면 `TestClient`·`curl`로 예시 본문을 수정 없이 보내 정상 응답을 확인한다.
- 실행 명령은 [`docs/conventions/testing.md`](docs/conventions/testing.md)에 있다.
- 린트는 [2.2](#22-린터-및-포매터)를 따른다.

## 4. 커밋 전 사용자 검토

- **커밋을 생성하기 전에 커밋 제목과 본문을 사용자에게 보여주고 검토를 받는다.** 사용자가 승인하기 전에는 `git commit`을 실행하지 않는다.
- 사용자가 수정을 요청하면 반영한 내용을 다시 보여주고 승인을 받은 뒤 커밋한다.
- **한 번의 요청에서 커밋을 여러 개 만들 때도 예외 없이 적용한다.**
  - 커밋을 나눈 기준, 커밋별로 포함되는 파일, 각 커밋의 제목과 본문을 순서대로 한 번에 보여주고 검토를 받는다.
  - 승인받은 내용 그대로, 보여준 순서대로 커밋을 생성한다.
  - 검토 중 커밋 구성이 바뀌면 바뀐 전체 구성을 다시 보여주고 승인을 받는다.

```
커밋 2개로 나눠 만들려고 합니다. 검토 부탁드립니다.

[1/2] app/schemas/user.py, app/exceptions/user.py
feat: 사용자 요청·응답 스키마와 도메인 예외 추가

- 생성·조회에 사용할 요청·응답 스키마를 추가한다
- 이메일이 중복일 때 쓸 도메인 예외를 정의한다

[2/2] app/api/v1/endpoints/user.py, app/services/user_service.py
feat: 사용자 생성 API 엔드포인트 추가

- `POST /users`로 사용자를 생성한다
- 중복 이메일은 409로 응답한다
```
