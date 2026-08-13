# 개인정보 보호와 공통 LLM 처리

> 관련 GitHub Issue: [#19](https://github.com/ams-3-idiots/untangle-ai/issues/19)

구현 전 초안이다. 구현 과정에서 확정한 내용을 이 문서에 반영한다.

## 1. 핵심 결정

- LLM provider는 OpenAI structured output을 사용한다 (Spring은 Anthropic
  Claude). 응답 계약은 Spring과 동일하게 유지한다.
- 앱은 원문을 그대로 보낸다. 개인정보 마스킹은 서버가 LLM으로 나가는 경계에서
  처리하고, API 응답에서는 원문으로 복원한다.
- provider 실패와 잘못된 모델 응답은 모두 `503` 하나로 변환한다.
- 애플리케이션 로그와 오류 응답에 사용자 입력·대화·프롬프트·모델 원문을 남기지
  않는다.

## 2. 상세 설계

### 2.1 마스킹과 복원

- LLM에 전달되는 페이로드에는 개인정보 원문이 포함되지 않는다.
- API 응답의 자유 텍스트 필드에서는 마스킹이 복원되어 원문이 내려간다.
- 마스킹 대상 항목의 상세는 구현에서 정한다.

### 2.2 오류 변환

다음은 모두 `503` ProblemDetail(`title: "AI service unavailable"`)로 변환한다.
본문 형식은 `docs/specs/17-spring-compatible-http-base.md`의 공통 오류 계약을
따른다.

- provider 설정(API key 등) 누락
- timeout·네트워크·SDK 호출 실패
- 스키마를 벗어난 모델 응답
- 사용 가능한 결과가 없는 모델 응답

### 2.3 호환성 테스트 사례

외부 OpenAI 호출 없이 fake LLM으로 검증한다.

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| T-01 | provider 설정(API key 등) 누락 | `503` ProblemDetail (`title: "AI service unavailable"`) |
| T-02 | timeout·네트워크·SDK 예외 | `503` ProblemDetail |
| T-03 | 스키마를 벗어난 모델 응답, 사용 가능한 결과가 없는 모델 응답 | `503` ProblemDetail |
| T-04 | 전화번호가 포함된 입력 | LLM에 전달되는 페이로드에 원문 없음(마스킹), API 응답 필드에는 원문 복원 |
| T-05 | 오류 응답(`404`·`422`·`429`·`503`) 및 애플리케이션 로그 | 사용자 입력·대화·프롬프트·모델 원문 미포함 |
