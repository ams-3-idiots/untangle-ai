"""헬스 체크 API의 요청과 응답을 검증한다."""

from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient):
    # 준비: 이 테스트에는 별도의 요청 데이터가 없다.

    # 실행
    response = client.get("/api/v1/health")

    # 확인
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
