# 개발 가이드라인

## 0. 목차

1. [프로젝트 구조](#1-프로젝트-구조) — 레이어 역할과 의존 방향, 이름 규칙
2. [린터 및 포매터](#2-린터-및-포매터) — Ruff 실행과 검증 기준
3. [Git Branch](#3-git-branch) — 브랜치 이름과 분기 기준
4. [Git Commit](#4-git-commit) — 접두어와 메시지 작성
5. [GitHub PR](#5-github-pr) — 제목·본문 구성

## 1. 프로젝트 구조

### 1.1 레이어와 역할

| 디렉토리 | 역할 |
| --- | --- |
| `app/main.py` | 앱 시작점 |
| `app/api/` | HTTP 엔드포인트 |
| `app/services/` | 비즈니스 로직 |
| `app/repositories/` | DB 조회·저장 |
| `app/models/` | DB 테이블 정의 |
| `app/schemas/` | 요청·응답 형식 |
| `app/exceptions/` | 도메인 예외와 HTTP 오류 변환 |
| `app/db/` | DB 연결과 세션 |

### 1.2 의존 방향

```
main → api → services → repositories → models

schemas : api, services 가 참조
exceptions : 도메인 예외와 HTTP 응답 변환을 관리한다.
             services는 도메인 예외를 참조하고, main은 예외 핸들러를 등록한다.
db      : 엔진·세션 팩토리·세션 주입 의존성과 Base 를 제공.
          api(세션 주입), models(Base 상속) 가 참조하며, db 는 다른 레이어를 참조하지 않는다.
```
- **의존 방향이 어긋나는 코드는 절대 작성하지 않습니다.**

### 1.3 데이터 흐름과 책임

```
요청 → endpoint  : schemas 로 형식 검증
     → service   : 업무 규칙 판단, 트랜잭션 경계
     → repository: 쿼리 실행 (flush 까지)
     → model / DB
응답 ← endpoint  : services가 반환한 schemas DTO를 response_model로 직렬화
```

- **데이터 검증**: 타입·필수값·형식은 `schemas`, 비즈니스 로직 관련 검증(중복 이메일, 권한 등)은 `services`.
- **예외 처리**: `services`는 `exceptions`에 정의된 도메인 예외를 발생시키며 `HTTPException`을 사용하지 않는다. 도메인 예외를 HTTP 상태 코드와 응답 본문으로 변환하는 처리도 `exceptions`에서 관리하고, `main.py`는 예외 핸들러를 애플리케이션에 등록한다.
- **세션**: 엔진·세션 팩토리·요청 단위 주입 의존성을 모두 `db/session.py`에 둔다.
  엔드포인트는 `DbSession` 별칭으로 세션을 받고, `services`는 세션을 인자로만 받는다.
  요청 밖(배치·CLI·테스트)에서는 `with SessionLocal() as db:` 로 직접 연다.
  접속 정보는 설정에서 읽고 `db/session.py`에 하드코딩하지 않는다.
  `api/dependencies.py`에는 DB 외의 요청 단위 의존성(현재 사용자, 페이지네이션 등)만 둔다.

```python
# app/db/session.py
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker


# engine은 같은 파일에서 설정의 DB URL로 생성한다.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
```

- **트랜잭션**: 업무 판단에 따른 `commit`·`rollback`은 `services`에서 한다.
  `repositories`는 `flush`까지만 하고 `commit`하지 않는다.
  예외가 밖으로 전파될 때의 정리용 `rollback`과 `close`는 `get_db`가 책임진다.
- **응답 DTO**: `services`는 `repositories`가 반환한 모델을 `schemas`에 정의된 응답 DTO로 변환한다.
  엔드포인트는 `models`를 직접 참조하지 않고 `services`가 반환한 DTO만 반환한다.
- **엔드포인트 선언**: 동기 세션을 쓰므로 엔드포인트는 `def`로 선언한다.

```python
# services/user_service.py
def create_user(db: Session, payload: UserCreate) -> UserRead:
    if user_repository.get_by_email(db, payload.email):
        raise DuplicateEmailError(payload.email)  # exceptions에 정의된 도메인 예외
    user = user_repository.create(
        db, payload
    )  # autoflush=False 이므로 repository 가 직접 flush
    db.commit()  # 트랜잭션 경계는 service
    return UserRead.model_validate(user, from_attributes=True)
```

```python
# api/v1/endpoints/user.py
@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: DbSession) -> UserRead:  # 동기 세션이므로 def
    return user_service.create_user(db, payload)
```

### 1.4 파일 이름 규칙

| 위치 | 규칙 | 예 |
| --- | --- | --- |
| `api/v1/endpoints/` | 도메인 단수형 | `user.py` |
| `models/`, `schemas/` | 도메인 단수형 | `user.py` |
| `services/` | `<도메인>_service.py` | `user_service.py` |
| `repositories/` | `<도메인>_repository.py` | `user_repository.py` |

- 한 도메인은 레이어마다 같은 이름 축을 유지한다: `user` → `user.py` / `user_service.py` / `user_repository.py`
- 파일이 커지면 쪼개지 말고 같은 이름의 패키지로 승격한다: `user_service.py` → `user_service/`
- API 버전이 올라가면 `api/v2/`를 새로 만들고 `v1`은 그대로 둔다.

### 1.5 새 기능 추가 순서

1. `models/` — 테이블 정의와 Alembic 마이그레이션
2. `schemas/` — 요청·응답 스키마
3. `repositories/` — 쿼리
4. `services/` — 유스케이스와 트랜잭션 경계
5. `api/v1/endpoints/` — 엔드포인트
6. `api/v1/router.py` — 라우터 등록

로직이 거의 없어도 5번에서 4번을 건너뛰지 않는다. 기존 레이어로 설명되지 않는 코드가 생기면 새 디렉토리를 만들기 전에 사용자에게 확인한다.

## 2. 린터 및 포매터

- Python 코드의 린터와 포매터로 Ruff를 사용한다.
- 코드 변경 후 `uv run ruff format .`으로 포맷을 적용한다.
- 작업 완료 전 `uv run ruff check .`을 실행하고 모든 린트 오류를 해결한다.
- 자동 수정이 필요한 경우 `uv run ruff check --fix .`을 실행한 뒤, `uv run ruff format .`과 `uv run ruff check .`을 다시 실행한다.
- 린트 규칙을 무시하거나 검사 대상에서 제외하는 설정은 사용자 확인 없이 추가하지 않는다.

## 3. Git Branch

### 이름
- `<구분>/<짧은-설명>` 형식.
  - 브랜치 `<구분>/<짧은-설명>`은 영어로 작성
  - 구분: `feat`, `fix`, `docs`, `refactor`, `chore`
  - 예: `feat/document-upload-api`, `fix/token-refresh-race`, `refactor/db-session-scope`

### 분기 기준
- 사용자가 따로 명시하지 않았다면 브랜치는 최신 `main`에서 분기한다.

## 4. Git Commit

### 제목
- `접두어: <메시지>` 형식
- 접두어는 아래 표를 참고하고, 메시지는 한국어로 작성

| 접두어 | 사용 |
| --- | --- |
| `feat` | 기능 추가·변경 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 (`docs/`, `README`, `AGENTS.md`, `CLAUDE.md`) |
| `refactor` | 동작 변화 없는 코드 구조 개선 |
| `chore` | 의존성·설정·빌드 등 (`pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`, CI 설정) |

### 본문

- 메시지 본문은 전부 한국어로 쓴다.
- 제목은 요약형으로 한 줄. 바뀐 코드 중에 가장 중요하다고 생각하는 변경 사항이 드러나게 적는다.
- 본문에는 변경 내용을 한국어로 서술한다.


### 예시

**`feat` — 기능 추가**

```
feat: 문서 업로드 API 엔드포인트 추가

`POST /documents`로 멀티파트 업로드를 받아 오브젝트 스토리지에 저장하고
메타데이터를 `documents` 테이블에 기록한다.
업로드 용량과 허용 확장자를 검증해 초과 시 413/415로 응답한다.
```

**`fix` — 버그 수정**

```
fix: 액세스 토큰 갱신 시 동시 요청 경합 수정

만료 직전 요청이 동시에 들어오면 리프레시 토큰이 중복 사용돼 401이 발생하던 문제를 수정한다.
갱신 구간에 사용자 단위 락을 걸고, 회전 직후 짧은 유예 시간 동안은 이전 토큰 재사용을 허용한다.
```

**`docs` — 문서 변경**

```
docs: README에 로컬 개발 환경 구성 방법 추가

`uv sync`로 의존성을 설치하고 개발 서버를 실행하는 순서를 README에 정리한다.
DB 컨테이너 기동과 마이그레이션 적용 절차, 환경 변수 예시를 함께 추가한다.
```

**`refactor` — 구조 개선**

```
refactor: 엔드포인트의 DB 접근 코드를 repository로 분리

엔드포인트에서 직접 실행하던 조회 쿼리를 `user_repository`로 옮긴다.
엔드포인트는 서비스만 호출하고, 커밋은 서비스에서 한 번만 수행하도록 정리한다.
```

**`chore` — 의존성·설정·빌드**

```
chore: 의존성 및 Docker 빌드 설정 정리

미사용 패키지를 제거하고 남은 의존성을 최신 버전으로 업데이트한다.
Dockerfile을 멀티스테이지로 나눠 런타임 이미지 크기를 줄이고 pyproject.toml과 uv.lock을 동기화한다.
```


## 5. GitHub PR

- `gh` CLI를 사용하여 작업.
### 5.1 제목
- [`카테고리`] `한 줄 설명` 
- `카테고리`: 어디를 변경했는지 또는 어떤 기능을 건드렸는지 등의 이번 작업에서 주로 다룬 것을 짧은 단어로 표현
- `한 줄 설명`: 수행한 일을 간단하게 한 줄로 서술
- `카테고리`가 목적어라면 `한 줄 설명`은 서술어

### 5.2 본문
- `목적`: 무엇을 달성하기 위해서 이 작업을 수행했는지 핵심만 두 줄 이하로 설명
- `변경 사항`: **변경된 모든 내용을 적는 게 목표가 아니며 목적을 달성하기 위해 수정 또는 추가한 내용이 무엇인지 다른 사람이 알 수 있게 해야 한다.**

### 5.3 예시
```
제목: [문서 업로드] 업로드 API와 메타데이터 저장 추가

## 목적
클라이언트가 분석 대상 파일을 서버에 올릴 수 있어야 하므로
업로드 엔드포인트와 메타데이터 저장 흐름을 추가한다.

## 변경 사항
- `app/api/v1/endpoints/document.py` 추가: `POST /documents` 멀티파트 업로드 처리
- `app/services/document_service.py`, `app/repositories/document_repository.py` 추가: 저장 흐름과 쿼리 분리
- `app/models/document.py`, `alembic/versions/0004_add_documents.py` 추가: 문서 메타데이터 테이블과 마이그레이션
- 용량·확장자 검증 실패 시 413/415를 반환하는 예외 핸들러 추가
```

```
제목: [토큰 갱신] 동시 요청 시 401 발생 문제 수정

## 목적
토큰 만료 직전 동시 요청에서 리프레시 토큰이 중복 사용돼 로그아웃되던 문제를 해결해
세션 유지 흐름을 정상화한다.

## 변경 사항
- 리프레시 처리에 사용자 단위 락을 적용해 동시 갱신을 직렬화
- 회전 직후 짧은 유예 시간 동안 이전 토큰 재사용을 허용
- 갱신 실패 경로에 구조화 로그를 추가해 원인 추적이 가능하도록 변경
```
