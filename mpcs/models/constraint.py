"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Constraint Definition

SRS §8 Constraint Module:
    §8.1 수학적 관계식을 통해 모노머 간 제약을 정의한다.
    §8.2 지원 표현식 예: HDI = PLA + SMA - 1
    §8.3 지원 연산자: + - * / ^ ( )
    §8.4 지원 비교: = < <= > >=
    §8.5 지원 함수: ABS() ROUND() INT()
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Constraint:
    """
    모노머 간 수학적 관계를 표현하는 제약식.

    SRS §8 Constraint Module 준수.

    Attributes:
        expression: 제약식 문자열 (예: "HDI = PLA + SMA - 1")
        is_active:  활성화 여부 (비활성화된 제약식은 솔버가 무시)

    제약식은 ConstraintEngine(services 레이어)에 의해 파싱·평가된다.
    이 dataclass는 순수 데이터 컨테이너 역할만 수행한다.

    사용 예:
        c = Constraint("HDI = PLA + SMA - 1")
        c2 = Constraint("EO = 45 * PLA", is_active=False)
    """

    expression: str
    is_active: bool = True

    def validate(self) -> list[str]:
        """
        기본적인 구문 유효성을 검사한다.
        심층 파싱은 ConstraintEngine에서 수행한다.

        Returns:
            오류 메시지 리스트. 빈 리스트 = 정상.
        """
        errors: list[str] = []

        if not self.expression or not self.expression.strip():
            errors.append("제약식이 비어 있습니다")
            return errors

        expr = self.expression.strip()

        # 지원 비교 연산자 중 하나가 존재해야 한다
        _COMPARISON_OPS = (">=", "<=", ">", "<", "=")
        has_comparison = any(op in expr for op in _COMPARISON_OPS)
        if not has_comparison:
            errors.append(
                f"제약식에 비교 연산자(= < <= > >=)가 없습니다: '{expr}'"
            )

        # 괄호 균형 검사
        depth = 0
        for ch in expr:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth < 0:
                errors.append("괄호가 올바르게 닫히지 않았습니다 (닫힘이 먼저)")
                break
        if depth != 0:
            errors.append(f"괄호 불균형: 열림 {depth}개 초과")

        return errors

    def __str__(self) -> str:
        status = "활성" if self.is_active else "비활성"
        return f"[{status}] {self.expression}"
