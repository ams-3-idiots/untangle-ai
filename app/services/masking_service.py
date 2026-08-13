"""LLM으로 나가는 텍스트의 개인정보를 가리고 모델 응답에서 원문으로 되돌린다.

대응표는 요청 하나 안에서만 살아 있고 저장하지 않는다 — 표 자체가 민감 정보다.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# 주민번호를 전화보다 먼저 찾아야 뒷자리가 전화 패턴에 먼저 걸리지 않는다.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\d{6}-[1-4]\d{6}"), "주민번호"),
    (re.compile(r"\d{4}-\d{4}-\d{4}-\d{4}"), "카드번호"),
    (re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "전화"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "이메일"),
)


@dataclass
class MaskingContext:
    """요청 하나가 쓰는 마스킹 표기와 원문의 대응표."""

    _originals: dict[str, str] = field(default_factory=dict)
    _placeholders: dict[str, str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def mask(self, text: str) -> str:
        """개인정보로 보이는 부분을 `[전화1]` 같은 표기로 바꾼다."""
        masked = text
        for pattern, label in _PATTERNS:
            masked = pattern.sub(self._replacer(label), masked)
        return masked

    def unmask(self, text: str) -> str:
        """이 요청에서 만든 표기를 원문으로 되돌린다."""
        restored = text
        for placeholder, original in self._placeholders.items():
            restored = restored.replace(placeholder, original)
        return restored

    def _replacer(self, label: str) -> Callable[[re.Match[str]], str]:
        """라벨을 고정한 정규식 치환 함수를 만든다."""

        def replace(match: re.Match[str]) -> str:
            return self._placeholder_for(match.group(), label)

        return replace

    def _placeholder_for(self, original: str, label: str) -> str:
        """같은 값이 늘 같은 표기를 받도록 대응표에서 찾거나 새로 만든다."""
        known = self._originals.get(original)
        if known is not None:
            return known
        index = self._counts.get(label, 0) + 1
        self._counts[label] = index
        placeholder = f"[{label}{index}]"
        self._originals[original] = placeholder
        self._placeholders[placeholder] = original
        return placeholder


def new_context() -> MaskingContext:
    """요청 하나가 쓸 새 마스킹 컨텍스트를 만든다."""
    return MaskingContext()
