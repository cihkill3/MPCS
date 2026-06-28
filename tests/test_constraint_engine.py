"""
MPCS 단위 테스트: ConstraintEngine

SRS §8 Constraint Module 검증
"""

import pytest
from mpcs.models.constraint import Constraint
from mpcs.services.constraint_engine import (
    ConstraintEngine,
    ConstraintParseError,
    CircularDependencyError,
)


class TestConstraintEngine:
    """ConstraintEngine 단위 테스트."""

    def setup_method(self):
        self.engine = ConstraintEngine()
        self.monomer_names = ["EO", "LA", "HDI", "PLA", "SMA"]

    # ── 파싱 테스트 ─────────────────────────────────────────────

    def test_parse_equality(self):
        """등식 제약식 파싱."""
        parsed = self.engine._parse_single("HDI = PLA + SMA - 1", self.monomer_names)
        assert parsed.comparison == "="
        assert parsed.equality_lhs == "HDI"
        assert "PLA" in parsed.free_vars
        assert "SMA" in parsed.free_vars

    def test_parse_multiplication(self):
        """곱셈 제약식: EO = 45 * PLA."""
        parsed = self.engine._parse_single("EO = 45 * PLA", self.monomer_names)
        assert parsed.equality_lhs == "EO"
        assert "PLA" in parsed.free_vars

    def test_parse_power_operator(self):
        """거듭제곱 연산자 (^)."""
        parsed = self.engine._parse_single("EO = PLA ^ 2", self.monomer_names)
        assert parsed.equality_lhs == "EO"

    def test_parse_inequality_le(self):
        """부등식 <= 파싱."""
        parsed = self.engine._parse_single("EO <= 100", self.monomer_names)
        assert parsed.comparison == "<="
        assert parsed.equality_lhs is None

    def test_parse_inequality_ge(self):
        """부등식 >= 파싱."""
        parsed = self.engine._parse_single("LA >= 10", self.monomer_names)
        assert parsed.comparison == ">="

    def test_parse_abs_function(self):
        """ABS() 함수 (SRS §8.5)."""
        parsed = self.engine._parse_single("EO = ABS(PLA - 5)", self.monomer_names)
        assert parsed.equality_lhs == "EO"

    def test_parse_unknown_variable_raises(self):
        """정의되지 않은 변수 → ConstraintParseError."""
        with pytest.raises(ConstraintParseError, match="정의되지 않은 변수"):
            self.engine._parse_single("UNKNOWN = PLA + 1", self.monomer_names)

    def test_parse_empty_raises(self):
        """빈 표현식 → ConstraintParseError."""
        with pytest.raises(ConstraintParseError):
            self.engine._parse_single("", self.monomer_names)

    def test_parse_no_comparison_raises(self):
        """비교 연산자 없음 → ConstraintParseError."""
        with pytest.raises(ConstraintParseError):
            self.engine._parse_single("PLA + SMA", self.monomer_names)

    # ── resolve 테스트 ──────────────────────────────────────────

    def test_resolve_simple_equality(self):
        """HDI = PLA + SMA - 1, PLA=2, SMA=10 → HDI=11."""
        parsed = self.engine._parse_single("HDI = PLA + SMA - 1", self.monomer_names)
        result = self.engine.resolve(parsed, {"PLA": 2, "SMA": 10})
        assert result == 11

    def test_resolve_multiplication(self):
        """EO = 45 * PLA, PLA=2 → EO=90."""
        parsed = self.engine._parse_single("EO = 45 * PLA", self.monomer_names)
        result = self.engine.resolve(parsed, {"PLA": 2})
        assert result == 90

    def test_resolve_non_integer_returns_none(self):
        """비정수 결과 → None (Q3 가정)."""
        parsed = self.engine._parse_single("EO = PLA / 3", self.monomer_names)
        # PLA=2 → EO = 2/3 (비정수)
        result = self.engine.resolve(parsed, {"PLA": 2})
        assert result is None

    def test_resolve_negative_returns_none(self):
        """음수 결과 → None."""
        parsed = self.engine._parse_single("HDI = PLA - 10", self.monomer_names)
        result = self.engine.resolve(parsed, {"PLA": 5})
        assert result is None

    def test_resolve_non_equality_returns_none(self):
        """등식이 아닌 제약식 → None."""
        parsed = self.engine._parse_single("EO >= 10", self.monomer_names)
        result = self.engine.resolve(parsed, {"EO": 15})
        assert result is None

    # ── evaluate 테스트 ─────────────────────────────────────────

    def test_evaluate_equality_satisfied(self):
        """등식 만족."""
        parsed = self.engine._parse_single("HDI = PLA + SMA - 1", self.monomer_names)
        assert self.engine.evaluate(parsed, {"HDI": 11, "PLA": 2, "SMA": 10})

    def test_evaluate_equality_violated(self):
        """등식 위반."""
        parsed = self.engine._parse_single("HDI = PLA + SMA - 1", self.monomer_names)
        assert not self.engine.evaluate(parsed, {"HDI": 5, "PLA": 2, "SMA": 10})

    def test_evaluate_le_satisfied(self):
        """부등식 <= 만족."""
        parsed = self.engine._parse_single("EO <= 100", self.monomer_names)
        assert self.engine.evaluate(parsed, {"EO": 50})

    def test_evaluate_ge_violated(self):
        """부등식 >= 위반."""
        parsed = self.engine._parse_single("LA >= 10", self.monomer_names)
        assert not self.engine.evaluate(parsed, {"LA": 5})

    # ── 위상 정렬 테스트 ────────────────────────────────────────

    def test_topological_sort_simple(self):
        """단순 의존성 정렬: HDI는 PLA, SMA에 의존."""
        c1 = Constraint("HDI = PLA + SMA - 1")
        c2 = Constraint("EO = 45 * PLA")
        parsed = self.engine.parse_all([c1, c2], self.monomer_names)
        sorted_pc = self.engine.topological_sort(parsed)
        # HDI는 PLA에 의존하지 않으므로 순서 무관
        assert len(sorted_pc) == 2

    def test_circular_dependency_raises(self):
        """순환 의존성 → CircularDependencyError (Q6)."""
        # A = B + 1, B = A + 1 은 순환
        names = ["A", "B"]
        c1 = Constraint("A = B + 1")
        c2 = Constraint("B = A + 1")
        parsed = self.engine.parse_all([c1, c2], names)
        with pytest.raises(CircularDependencyError):
            self.engine.topological_sort(parsed)

    # ── 전체 파이프라인 ─────────────────────────────────────────

    def test_srs_example_full_pipeline(self):
        """
        SRS §8.2 예시 전체 파이프라인:
            HDI = PLA + SMA - 1
            EO = 45 * PLA
            LA = 26 * PLA
            SMA = 5 * PLA

        PLA=2 가정 시:
            SMA = 10, LA = 52, EO = 90, HDI = 11
        """
        names = ["EO", "LA", "HDI", "PLA", "SMA"]
        constraints = [
            Constraint("HDI = PLA + SMA - 1"),
            Constraint("EO = 45 * PLA"),
            Constraint("LA = 26 * PLA"),
            Constraint("SMA = 5 * PLA"),
        ]
        parsed = self.engine.parse_all(constraints, names)
        sorted_pc = self.engine.topological_sort(parsed)

        values: dict[str, int] = {"PLA": 2}
        for pc in sorted_pc:
            if pc.equality_lhs:
                val = self.engine.resolve(pc, values)
                assert val is not None, f"{pc.equality_lhs} 결정 실패"
                values[pc.equality_lhs] = val

        assert values["SMA"] == 10
        assert values["LA"] == 52
        assert values["EO"] == 90
        assert values["HDI"] == 11
