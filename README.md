# untangle-ai

FastAPI 기반 AI API 서버.

개발 규칙(레이어 구조, 코드 스타일)은 [AGENTS.md](AGENTS.md)에 있고,
테스트와 Git 규약은 [docs/conventions/](docs/conventions/)에 있다.

## 개발 환경 구성

```bash
uv sync
cp .env.example .env
```

영구 저장소를 쓰지 않으므로 DB 준비 없이 바로 실행할 수 있다.
`.env`의 `OPENAI_API_KEY`가 비어 있으면 AI 엔드포인트가 503으로 응답한다.

## 실행

```bash
uv run fastapi dev app/main.py
```

- 문서: <http://127.0.0.1:8000/docs>
- 헬스 체크: <http://127.0.0.1:8000/api/v1/health>

## 테스트

```bash
uv run pytest            # 전체
uv run pytest -k health  # 이름으로 선택
```

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
├── core/                      환경 설정과 문서용 고정 문자열
├── api/
│   ├── middleware.py          요청 단위 미들웨어
│   ├── dependencies.py        요청 단위 의존성
│   └── v1/
│       ├── router.py          v1 라우터 등록
│       └── endpoints/         HTTP 엔드포인트
├── services/                  업무 규칙, 상태 보관, 외부 호출
├── schemas/                   요청·응답 형식
└── exceptions/                도메인 예외와 HTTP 변환

tests/                         app/ 구조를 따라 배치
```
