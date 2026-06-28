"""
MPCS — MALDI Polymer Composition Solver
Core Layer: Molecular Formula Parser

SRS §6.1 Formula Input:
    사용자가 분자식을 입력할 수 있어야 한다 (예: C4H6O3).

SRS §6.3 Supported Elements:
    H, C, N, O, S, P, F, Cl, Br, I, Si, B, Na, K, Li, Mg, Ca, Zn

지원 형식:
    - 기본: C4H6O3
    - 괄호 (중첩 가능): C2H5(OH)3, Ca3(PO4)2
    - 소문자 없는 단일 원소: H2O, NaCl
    - 계수 없는 원소: 계수 1로 처리 (예: CH4 → C1H4)
"""

from __future__ import annotations

import re
from typing import Final

from mpcs.core.atomic_mass_db import AtomicMassDB


# 원소 기호 정규식: 대문자 + 선택적 소문자 1개
_ELEMENT_PATTERN: Final[str] = r"([A-Z][a-z]?)(\d*)"
_ELEMENT_RE: Final[re.Pattern[str]] = re.compile(_ELEMENT_PATTERN)


class FormulaParseError(ValueError):
    """분자식 파싱 오류."""

    def __init__(self, formula: str, reason: str) -> None:
        self.formula = formula
        self.reason = reason
        super().__init__(f"분자식 파싱 오류 '{formula}': {reason}")


class FormulaParser:
    """
    분자식 문자열을 원소 카운트 딕셔너리로 변환한다.

    SRS §6.1, §6.3 준수.

    사용 예:
        parser = FormulaParser()
        elements = parser.parse("C4H6O3")
        # {'C': 4, 'H': 6, 'O': 3}

        elements = parser.parse("Ca3(PO4)2")
        # {'Ca': 3, 'P': 2, 'O': 8}

    지원 원소:
        AtomicMassDB.SUPPORTED_ELEMENTS 와 동일.

    Raises:
        FormulaParseError: 빈 문자열, 미지원 원소, 괄호 불일치, 음수 계수 등
    """

    def parse(self, formula: str) -> dict[str, int]:
        """
        분자식 문자열을 파싱하여 원소별 원자 수를 반환한다.

        Args:
            formula: 분자식 문자열 (예: "C4H6O3", "Ca3(PO4)2")

        Returns:
            원소 기호 → 원자 수 딕셔너리 (원자 수 > 0인 원소만 포함)

        Raises:
            FormulaParseError: 파싱 실패 시
        """
        formula = formula.strip()
        if not formula:
            raise FormulaParseError(formula, "빈 문자열은 허용되지 않습니다")

        try:
            counts, remaining = self._parse_segment(formula, 0)
        except FormulaParseError:
            raise
        except Exception as exc:
            raise FormulaParseError(formula, f"파싱 중 예외 발생: {exc}") from exc

        if remaining != len(formula):
            raise FormulaParseError(
                formula,
                f"파싱 실패: 위치 {remaining}부터 인식 불가 ({formula[remaining:]!r})"
            )

        # 지원 원소 검증
        for element in counts:
            if not AtomicMassDB.is_supported(element):
                supported = ", ".join(AtomicMassDB.supported_elements())
                raise FormulaParseError(
                    formula,
                    f"지원하지 않는 원소 '{element}'. 지원 원소: {supported}"
                )

        return {elem: cnt for elem, cnt in counts.items() if cnt > 0}

    # ------------------------------------------------------------------
    # Internal parsing implementation
    # ------------------------------------------------------------------

    def _parse_segment(
        self, formula: str, pos: int
    ) -> tuple[dict[str, int], int]:
        """
        pos 위치부터 한 세그먼트(괄호 블록 또는 원소 나열)를 파싱한다.

        Returns:
            (원소_카운트, 다음_파싱_위치)
        """
        counts: dict[str, int] = {}
        length = len(formula)

        while pos < length:
            ch = formula[pos]

            if ch == "(":
                # 괄호 블록 시작
                inner_counts, pos = self._parse_segment(formula, pos + 1)
                if pos >= length or formula[pos] != ")":
                    raise FormulaParseError(formula, "괄호가 닫히지 않았습니다")
                pos += 1  # ')' 소비

                # ')' 뒤 숫자 읽기
                multiplier, pos = self._read_int(formula, pos)
                if multiplier == 0:
                    multiplier = 1

                for elem, cnt in inner_counts.items():
                    counts[elem] = counts.get(elem, 0) + cnt * multiplier

            elif ch == ")":
                # 상위 호출에서 처리 — 현재 위치 반환
                break

            elif ch.isupper():
                # 원소 기호 파싱
                elem, pos = self._read_element(formula, pos)
                count, pos = self._read_int(formula, pos)
                if count == 0:
                    count = 1
                counts[elem] = counts.get(elem, 0) + count

            else:
                raise FormulaParseError(
                    formula,
                    f"위치 {pos}: 예상치 못한 문자 {ch!r}"
                )

        return counts, pos

    @staticmethod
    def _read_element(formula: str, pos: int) -> tuple[str, int]:
        """
        pos 위치에서 원소 기호를 읽는다.
        대문자 1개 + 선택적 소문자 1개.

        Returns:
            (원소_기호, 다음_위치)
        """
        length = len(formula)
        start = pos
        pos += 1  # 대문자 소비

        # 소문자 1개 옵션
        if pos < length and formula[pos].islower():
            pos += 1

        return formula[start:pos], pos

    @staticmethod
    def _read_int(formula: str, pos: int) -> tuple[int, int]:
        """
        pos 위치에서 연속된 숫자를 읽는다.

        Returns:
            (정수값, 다음_위치). 숫자 없으면 (0, pos).
        """
        length = len(formula)
        start = pos
        while pos < length and formula[pos].isdigit():
            pos += 1

        if start == pos:
            return 0, pos

        value = int(formula[start:pos])
        return value, pos
