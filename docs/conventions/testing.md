# 테스트 코드 규약

테스트를 작성·수정하거나 테스트 구조를 정할 때 읽는다.

- 이 문서는 `AGENTS.md`의 상시 규칙 위에서 적용된다. Docstring과 주석 규칙은 [`AGENTS.md` 2.1](../../AGENTS.md#21-docstring과-주석)을 따른다.
- 테스트를 실행하는 시점과 실패한 테스트를 다루는 원칙은 [`AGENTS.md` 3. 작업 완료 전 확인](../../AGENTS.md#3-작업-완료-전-확인)을 따른다.

테스트는 기능이 의도한 대로 동작하는지 자동으로 확인하는 코드다. FastAPI의 `TestClient`로 API에 요청을 보내고, pytest의 `assert`로 실제 결과가 기대한 결과와 같은지 확인한다.

## 0. 목차

1. [테스트 파일 구조와 이름](#1-테스트-파일-구조와-이름)
2. [첫 API 테스트 작성](#2-첫-api-테스트-작성)
3. [테스트에서 확인할 것](#3-테스트에서-확인할-것)
4. [테스트 실행](#4-테스트-실행)

## 1. 테스트 파일 구조와 이름

테스트는 프로젝트 루트의 `tests/`에 두고, 가능한 한 `app/`의 구조를 따라 배치한다.

```text
tests/
├── conftest.py                 # 여러 테스트가 함께 사용하는 fixture
├── api/
│   └── v1/
│       └── test_user.py        # 사용자 엔드포인트 테스트
└── services/
    └── test_user_service.py    # 사용자 비즈니스 로직 테스트
```

- 테스트 파일 이름은 `test_`로 시작한다: `test_user.py`.
- 테스트 함수 이름도 `test_`로 시작하고, 확인하려는 동작이 드러나게 쓴다: `test_create_user_returns_201`.
- 엔드포인트의 요청·응답은 `tests/api/`에서, 서비스의 업무 규칙은 `tests/services/`에서 테스트한다.
- 서로 다른 기능을 하나의 테스트 함수에서 한꺼번에 확인하지 않는다.

## 2. 첫 API 테스트 작성

여러 테스트에서 사용할 `TestClient`는 fixture로 만든다. fixture는 테스트 실행에 필요한 준비 작업을 대신하는 함수이며, 테스트 함수의 인자로 받아 사용한다.

`tests/conftest.py`:

```python
"""API 테스트에서 공통으로 사용하는 fixture를 제공한다."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """애플리케이션을 호출하는 테스트 클라이언트를 제공한다."""
    with TestClient(app) as test_client:
        yield test_client
```

테스트 함수는 **준비 → 실행 → 확인** 순서로 읽히게 작성한다. 아래 코드는 `/health` 엔드포인트가 정상 응답하는지 확인하는 예시다.

`tests/api/v1/test_health.py`:

```python
"""상태 확인 API의 요청과 응답을 검증한다."""

from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient):
    # 준비: 이 예시에는 별도의 요청 데이터가 없다.

    # 실행
    response = client.get("/api/v1/health")

    # 확인
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

`TestClient`를 사용하는 테스트 함수는 일반 `def`로 작성하고, 요청을 보낼 때 `await`를 사용하지 않는다. JSON 요청 본문은 `client.post('/users', json={...})`처럼 전달한다.

## 3. 테스트에서 확인할 것

- API 테스트는 최소한 **HTTP 상태 코드**와 **응답 본문**을 확인한다.
- 정상 요청 테스트를 먼저 작성하고, 잘못된 입력이나 존재하지 않는 데이터처럼 대표적인 실패 상황도 작성한다.
- 한 테스트가 실패했을 때 원인을 바로 알 수 있도록 한 가지 동작만 확인한다.
- 각 테스트는 다른 테스트가 만든 데이터나 실행 순서에 의존하지 않아야 한다.
- ID나 생성 시각처럼 매번 달라지는 값은 고정값 전체와 비교하지 말고, 필요한 필드의 존재 여부와 타입을 확인한다.
- 함수가 내부에서 어떤 함수를 호출했는지보다 사용자에게 보이는 요청·응답과 업무 규칙을 확인한다.

## 4. 테스트 실행

전체 테스트를 실행한다.

```bash
uv run pytest
```

특정 파일이나 이름에 해당하는 테스트만 실행할 수도 있다.

```bash
uv run pytest tests/api/v1/test_user.py
uv run pytest -k create_user
```

실행 시점과 실패 처리는 [`AGENTS.md` 3. 작업 완료 전 확인](../../AGENTS.md#3-작업-완료-전-확인)을 따른다.
