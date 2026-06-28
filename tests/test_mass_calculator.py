"""
MPCS 단위 테스트: FormulaParser + MassCalculator

SRS §6.2, §6.3, §6.4 준수 확인
SRS §22 Acceptance Criteria: "Correctly calculate exact masses from formulas"
"""

import pytest
from mpcs.core.formula_parser import FormulaParser, FormulaParseError
from mpcs.core.mass_calculator import MassCalculator, MassCalculationError
from mpcs.core.atomic_mass_db import AtomicMassDB


# ─── FormulaParser 테스트 ────────────────────────────────────────────────

class TestFormulaParser:
    """FormulaParser 단위 테스트."""

    def setup_method(self):
        self.parser = FormulaParser()

    def test_simple_formula(self):
        """기본 분자식 파싱."""
        result = self.parser.parse("C4H6O3")
        assert result == {"C": 4, "H": 6, "O": 3}

    def test_single_element(self):
        """단일 원소 (계수 없음 → 1)."""
        result = self.parser.parse("H2O")
        assert result == {"H": 2, "O": 1}

    def test_eo_monomer(self):
        """EO(ethylene oxide) 분자식: C2H4O."""
        result = self.parser.parse("C2H4O")
        assert result == {"C": 2, "H": 4, "O": 1}

    def test_la_monomer(self):
        """LA(lactic acid repeat unit) 분자식: C3H4O2."""
        result = self.parser.parse("C3H4O2")
        assert result == {"C": 3, "H": 4, "O": 2}

    def test_parentheses(self):
        """괄호 포함 분자식."""
        result = self.parser.parse("Ca3(PO4)2")
        assert result == {"Ca": 3, "P": 2, "O": 8}

    def test_nested_parentheses(self):
        """중첩 괄호."""
        result = self.parser.parse("C2H5(OH)3")
        assert result == {"C": 2, "H": 8, "O": 3}

    def test_two_letter_element(self):
        """두 글자 원소 기호 (Na, Cl 등)."""
        result = self.parser.parse("NaCl")
        assert result == {"Na": 1, "Cl": 1}

    def test_all_supported_elements(self):
        """SRS §6.3 지원 원소 18종 파싱 확인."""
        elements = AtomicMassDB.supported_elements()
        for elem in elements:
            result = self.parser.parse(f"{elem}2")
            assert elem in result

    def test_empty_formula_raises(self):
        """빈 문자열 → FormulaParseError."""
        with pytest.raises(FormulaParseError):
            self.parser.parse("")

    def test_unsupported_element_raises(self):
        """미지원 원소 (Au, Ag 등) → FormulaParseError."""
        with pytest.raises(FormulaParseError, match="지원하지 않는 원소"):
            self.parser.parse("Au3Cl")

    def test_unbalanced_parentheses_raises(self):
        """괄호 불균형 → FormulaParseError."""
        with pytest.raises(FormulaParseError):
            self.parser.parse("C2H5(OH")

    def test_srs_example_c4h6o3(self):
        """SRS §6.1 예시: C4H6O3."""
        result = self.parser.parse("C4H6O3")
        assert result == {"C": 4, "H": 6, "O": 3}


# ─── MassCalculator 테스트 ──────────────────────────────────────────────────

class TestMassCalculator:
    """MassCalculator 단위 테스트."""

    def setup_method(self):
        self.calc = MassCalculator()

    def test_water(self):
        """H₂O 정밀질량: 18.010565 Da."""
        mass = self.calc.calc_exact_mass("H2O")
        # H: 2×1.007825032 + O: 15.994914620 = 18.010565
        assert abs(mass - 18.010565) < 1e-5

    def test_eo_monomer(self):
        """EO(C2H4O) 정밀질량: ~44.026215 Da."""
        mass = self.calc.calc_exact_mass("C2H4O")
        # C: 2×12.0 + H: 4×1.007825 + O: 15.994915 = 44.026215
        expected = 2 * 12.0 + 4 * 1.00782503207 + 15.99491461956
        assert abs(mass - expected) < 1e-8

    def test_la_monomer(self):
        """LA(C3H4O2) 정밀질량 계산."""
        mass = self.calc.calc_exact_mass("C3H4O2")
        expected = 3 * 12.0 + 4 * 1.00782503207 + 2 * 15.99491461956
        assert abs(mass - expected) < 1e-8

    def test_srs_example_masses(self):
        """SRS §6.4 원소별 예시 검증."""
        assert abs(AtomicMassDB.get_mass("H") - 1.007825032) < 1e-8
        assert abs(AtomicMassDB.get_mass("C") - 12.0) < 1e-8
        assert abs(AtomicMassDB.get_mass("N") - 14.003074004) < 1e-8
        assert abs(AtomicMassDB.get_mass("O") - 15.994914620) < 1e-8

    def test_calc_from_elements(self):
        """원소 딕셔너리로 질량 계산."""
        elements = {"C": 4, "H": 6, "O": 3}
        mass = self.calc.calc_from_elements(elements)
        formula_mass = self.calc.calc_exact_mass("C4H6O3")
        assert abs(mass - formula_mass) < 1e-10

    def test_lru_cache_consistency(self):
        """동일 분자식 반복 계산 일관성 (캐시)."""
        m1 = self.calc.calc_exact_mass("C12H22O11")  # sucrose
        m2 = self.calc.calc_exact_mass("C12H22O11")
        assert m1 == m2

    def test_empty_formula_raises(self):
        """빈 문자열 → MassCalculationError."""
        with pytest.raises(MassCalculationError):
            self.calc.calc_exact_mass("")

    def test_validate_formula_valid(self):
        """유효한 분자식 검증."""
        errors = self.calc.validate_formula("C4H6O3")
        assert errors == []

    def test_validate_formula_invalid(self):
        """잘못된 분자식 검증."""
        errors = self.calc.validate_formula("Xx4H6")
        assert len(errors) > 0

    def test_hdi_monomer(self):
        """HDI(hexamethylene diisocyanate, C8H12N2O2) 정밀질량 계산."""
        mass = self.calc.calc_exact_mass("C8H12N2O2")
        expected = (8 * 12.0 + 12 * 1.00782503207
                    + 2 * 14.00307400480 + 2 * 15.99491461956)
        assert abs(mass - expected) < 1e-8
