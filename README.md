# untangle-ai

FastAPI + SQLAlchemy 기반 API 서버.

개발 규칙(레이어 구조, 코드 스타일)은 [AGENTS.md](AGENTS.md)에 있고,
테스트와 Git 규약은 [docs/conventions/](docs/conventions/)에 있다.

## 개발 환경 구성

```bash
uv sync
cp .env.example .env
```

`.env`의 `DATABASE_URL` 기본값은 로컬 SQLite 파일(`./untangle.db`)이라 별도 DB 없이
바로 실행할 수 있다.

## 개발용 스키마

마이그레이션 도구는 아직 도입하지 않았다. 개발용 DB의 테이블은 아래 명령으로 만든다.

```bash
uv run python -c "import app.models; from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(engine)"
```

새 모델을 만들면 `app/models/__init__.py`에 import 해야 이 명령이 인식한다.
스키마를 바꿨을 때는 `untangle.db`를 지우고 다시 실행한다.

## 실행

```bash
uv run fastapi dev app/main.py
```

- 문서: <http://127.0.0.1:8000/docs>
- 헬스 체크: <http://127.0.0.1:8000/api/v1/health>

## 테스트

```bash
uv run pytest                            # 전체
uv run pytest tests/api/v1/test_health.py  # 특정 파일
uv run pytest -k health                    # 이름으로 선택
```

테스트는 매번 새 인메모리 SQLite를 쓰므로 개발용 DB에 영향을 주지 않는다.

## 린터·포매터

```bash
uv run ruff format .
uv run ruff check .
uv run ruff check --fix .
```

## 디렉토리

```text
app/
├── main.py                    앱 시작점, 예외 핸들러·라우터 등록
├── core/config.py             환경 변수 기반 설정
├── api/
│   ├── dependencies.py        DB 외 요청 단위 의존성
│   └── v1/
│       ├── router.py          v1 라우터 등록
│       └── endpoints/         HTTP 엔드포인트
├── services/                  업무 규칙, 트랜잭션 경계
├── repositories/              쿼리 (flush 까지)
├── models/                    테이블 정의
├── schemas/                   요청·응답 형식
├── exceptions/                도메인 예외와 HTTP 변환
└── db/                        Base, 엔진, 세션 주입

tests/                         app/ 구조를 따라 배치
```
