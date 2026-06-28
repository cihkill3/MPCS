"""
MPCS — MALDI Polymer Composition Solver
Core Layer: Exact Mass Calculator

SRS §6.2 Automatic Exact Mass Calculation:
    분자식으로부터 단일동위원소 정밀질량을 자동 계산한다.

SRS §6.4:
    내장 원자 질량 DB를 사용한다.
"""

from __future__ import annotations

from functools import lru_cache

from mpcs.core.atomic_mass_db import AtomicMassDB
from mpcs.core.formula_parser import FormulaParser, FormulaParseError


class MassCalculationError(ValueError):
    """질량 계산 오류."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MassCalculator:
    """
    분자식 또는 원소 카운트로부터 단일동위원소 정밀질량을 계산한다.

    SRS §6.2, §6.4 준수.

    내부적으로 FormulaParser와 AtomicMassDB를 사용한다.
    동일 분자식에 대한 반복 계산은 LRU 캐시로 최적화한다.

    사용 예:
        calc = MassCalculator()
        mass = calc.calc_exact_mass("C4H6O3")   # 102.031694 Da
        mass = calc.calc_from_elements({"C": 4, "H": 6, "O": 3})  # 동일 결과
    """

    def __init__(
        self,
        db: AtomicMassDB | None = None,
        parser: FormulaParser | None = None,
    ) -> None:
        self._db = db or AtomicMassDB()
        self._parser = parser or FormulaParser()

    def calc_exact_mass(self, formula: str) -> float:
        """
        분자식 문자열로부터 단일동위원소 정밀질량을 계산한다.

        Args:
            formula: 분자식 문자열 (예: "C4H6O3", "C2H4O")

        Returns:
            단일동위원소 정밀질량 (Da)

        Raises:
            FormulaParseError: 분자식 파싱 실패
            MassCalculationError: 질량 계산 실패
        """
        formula = formula.strip()
        if not formula:
            raise MassCalculationError("빈 분자식은 허용되지 않습니다")

        return self._calc_exact_mass_cached(formula)

    @lru_cache(maxsize=1024)
    def _calc_exact_mass_cached(self, formula: str) -> float:
        """캐시를 적용한 내부 계산 메서드."""
        elements = self._parser.parse(formula)
        return self._sum_elements(elements)

    def calc_average_mass(self, formula: str) -> float:
        """분자식 문자열로부터 평균 질량을 계산한다."""
        formula = formula.strip()
        if not formula:
            raise MassCalculationError("빈 분자식은 허용되지 않습니다")
        return self._calc_average_mass_cached(formula)

    @lru_cache(maxsize=1024)
    def _calc_average_mass_cached(self, formula: str) -> float:
        elements = self._parser.parse(formula)
        return self._sum_average_elements(elements)

    def calc_average_from_elements(self, elements: dict[str, int]) -> float:
        """원소 카운트 딕셔너리로부터 평균 질량을 계산한다."""
        if not elements:
            raise MassCalculationError("원소가 없습니다")
        for elem, count in elements.items():
            if count < 0:
                raise MassCalculationError(f"원소 '{elem}'의 원자 수가 음수입니다: {count}")
        return self._sum_average_elements(elements)

    def _sum_average_elements(self, elements: dict[str, int]) -> float:
        """원소 딕셔너리의 평균 질량을 합산한다."""
        total_mass = 0.0
        for elem, count in elements.items():
            try:
                mass = self._db.get_average_mass(elem)
                total_mass += mass * count
            except KeyError as e:
                raise MassCalculationError(str(e)) from e
        return total_mass

    def calc_from_elements(self, elements: dict[str, int]) -> float:
        """
        원소 카운트 딕셔너리로부터 단일동위원소 정밀질량을 계산한다.

        Args:
            elements: {원소_기호: 원자_수} 딕셔너리
                      예: {"C": 4, "H": 6, "O": 3}

        Returns:
            단일동위원소 정밀질량 (Da)

        Raises:
            MassCalculationError: 빈 딕셔너리 또는 음수 원자 수
            KeyError: 지원하지 않는 원소
        """
        if not elements:
            raise MassCalculationError("원소가 없습니다")

        for elem, count in elements.items():
            if count < 0:
                raise MassCalculationError(
                    f"원소 '{elem}'의 원자 수가 음수입니다: {count}"
                )

        return self._sum_elements(elements)

    def calc_average_mass(self, formula: str) -> float:
        """분자식 문자열로부터 평균 질량을 계산한다."""
        formula = formula.strip()
        if not formula:
            raise MassCalculationError("빈 분자식은 허용되지 않습니다")
        return self._calc_average_mass_cached(formula)

    @lru_cache(maxsize=1024)
    def _calc_average_mass_cached(self, formula: str) -> float:
        elements = self._parser.parse(formula)
        return self._sum_average_elements(elements)

    def calc_average_from_elements(self, elements: dict[str, int]) -> float:
        """원소 카운트 딕셔너리로부터 평균 질량을 계산한다."""
        if not elements:
            raise MassCalculationError("원소가 없습니다")
        for elem, count in elements.items():
            if count < 0:
                raise MassCalculationError(f"원소 '{elem}'의 원자 수가 음수입니다: {count}")
        return self._sum_average_elements(elements)

    def _sum_average_elements(self, elements: dict[str, int]) -> float:
        """원소 딕셔너리의 평균 질량을 합산한다."""
        total_mass = 0.0
        for elem, count in elements.items():
            try:
                mass = self._db.get_average_mass(elem)
                total_mass += mass * count
            except KeyError as e:
                raise MassCalculationError(str(e)) from e
        return total_mass

    def _sum_elements(self, elements: dict[str, int]) -> float:
        """원소별 질량 합산."""
        total = 0.0
        for element, count in elements.items():
            total += AtomicMassDB.get_mass(element) * count
        return total

    def validate_formula(self, formula: str) -> list[str]:
        """
        분자식의 유효성을 검사하고 오류 메시지 목록을 반환한다.

        Args:
            formula: 분자식 문자열

        Returns:
            오류 메시지 리스트. 빈 리스트 = 정상.
        """
        errors: list[str] = []
        formula = formula.strip()

        if not formula:
            errors.append("분자식이 비어 있습니다")
            return errors

        try:
            elements = self._parser.parse(formula)
            if not elements:
                errors.append("유효한 원소를 찾을 수 없습니다")
        except FormulaParseError as exc:
            errors.append(str(exc.reason))

        return errors
