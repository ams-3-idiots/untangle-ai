"""LLM 전송 전 개인정보 마스킹과 응답 역치환 규칙을 검증한다."""

from app.services import masking_service

PHONE = "010-1234-5678"
EMAIL = "kim@corp.co.kr"
RRN = "900101-1234567"
CARD = "1234-5678-9012-3456"


def test_masks_phone_number():
    # 준비
    context = masking_service.new_context()

    # 실행
    masked = context.mask(f"김대리에게 {PHONE}로 연락")

    # 확인
    assert PHONE not in masked
    assert "[전화1]" in masked


def test_masks_email():
    context = masking_service.new_context()

    masked = context.mask(f"{EMAIL}로 회신하기")

    assert EMAIL not in masked
    assert "[이메일1]" in masked


def test_masks_resident_registration_number():
    context = masking_service.new_context()

    masked = context.mask(f"주민 {RRN} 확인")

    assert RRN not in masked
    assert "[주민번호1]" in masked


def test_masks_card_number():
    context = masking_service.new_context()

    masked = context.mask(f"카드 {CARD} 결제")

    assert CARD not in masked
    assert "[카드번호1]" in masked


def test_masks_phone_without_hyphens():
    context = masking_service.new_context()

    masked = context.mask("01012345678로 연락")

    assert "01012345678" not in masked


def test_same_value_gets_the_same_placeholder():
    context = masking_service.new_context()

    masked = context.mask(f"{PHONE}로 걸고 안 되면 {PHONE}로 문자")

    assert masked.count("[전화1]") == 2


def test_distinct_values_get_distinct_placeholders():
    context = masking_service.new_context()

    masked = context.mask("A: 010-1111-2222 / B: 010-3333-4444")

    assert "[전화1]" in masked
    assert "[전화2]" in masked


def test_text_without_personal_data_is_untouched():
    context = masking_service.new_context()

    assert context.mask("보고서 초안 쓰고 팀 리뷰 요청하기") == (
        "보고서 초안 쓰고 팀 리뷰 요청하기"
    )


def test_unmask_restores_the_original_value():
    # 준비: 마스킹한 요청에서 만들어진 표기를 모델이 되돌려준 상황이다.
    context = masking_service.new_context()
    context.mask(f"연락처 {PHONE}")

    restored = context.unmask("[전화1]로 전화하기")

    assert restored == f"{PHONE}로 전화하기"


def test_unmask_leaves_unknown_placeholder_alone():
    context = masking_service.new_context()

    assert context.unmask("[전화1]로 전화하기") == "[전화1]로 전화하기"


def test_contexts_do_not_share_the_mapping():
    # 준비: 다른 요청의 대응표로는 복원되지 않아야 한다.
    first = masking_service.new_context()
    first.mask(f"연락처 {PHONE}")

    second = masking_service.new_context()

    assert second.unmask("[전화1]") == "[전화1]"
