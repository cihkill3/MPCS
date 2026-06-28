"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Monomer Definition

SRS §5 Monomer Definition Module:
    §5.1 Monomer Table: Name, Type, Exact Mass, Formula, Min Count, Max Count
    §5.2 Supported Types: Monomer, Block, Crosslinker, End Group, Adduct

변경 이력:
    v1.1: BlockSubItem 추가 — Block 하위 성분 정의 (계층형 입력 지원)
          from_formula_or_mass() 추가 — 숫자는 직접 질량, 문자는 분자식으로 자동 구분
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class MonomerType(str, Enum):
    """
    모노머 유형 분류.

    SRS §5.2 Supported Types:
        Monomer    — 일반 반복단위 (예: EO, LA)
        Block      — 블록 공중합체의 블록 단위 (예: PLA-PEG-PLA)
                     하위 성분(BlockSubItem)을 가지며, 솔버에서 정수배로 처리됨.
        Crosslinker — 가교제 (예: HDI)
        End_Group  — 말단기 (SRS §5.2의 "End Group")
        Adduct     — 어덕트 이온 (SRS §5.2의 "Adduct")
    """

    MONOMER     = "Monomer"
    BLOCK       = "Block"
    CROSSLINKER = "Crosslinker"
    END_GROUP   = "End Group"
    ADDUCT      = "Adduct"


@dataclass
class BlockSubItem:
    """
    Block 모노머의 하위 성분.

    블록 1개에 포함되는 모노머/말단기/가교제를 정의한다.
    여러 BlockSubItem의 합이 Block 1개의 질량이 된다.

    예시:
        PLA-PEG-PLA 블록 내부:
          - LA (Monomer): count 20~30 per block, exact_mass 72.021 Da
          - EG (Monomer): count 40~50 per block, exact_mass 44.026 Da
          - H2O (End Group): count 1~1 per block, exact_mass 18.011 Da

    Attributes:
        name            표시 이름 (예: "LA", "EG", "H2O")
        sub_type        유형 (MONOMER / END_GROUP / CROSSLINKER)
        formula_or_mass 원본 입력값. 숫자면 직접 질량, 분자식이면 파싱값
        exact_mass      단일동위원소 정밀질량 (Da)
        count_min       블록 1개당 최소값 (정수)
        count_max       블록 1개당 최대값 (정수)
    """

    name: str
    sub_type: MonomerType
    formula_or_mass: str
    exact_mass: float
    average_mass: float = 0.0
    count_min: int = 1
    count_max: int = 1

    @property
    def count_avg(self) -> float:
        """블록 1개당 평균 개수."""
        return (self.count_min + self.count_max) / 2.0

    @property
    def mass_contribution_avg(self) -> float:
        """블록 1개당 평균 질량 기여 (Da)."""
        return self.count_avg * self.exact_mass

    @property
    def mass_contribution_average_mass(self) -> float:
        """블록 1개당 평균 질량(average mass) 기여 (Da)."""
        return self.count_avg * self.average_mass

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("하위 성분 이름이 비어 있습니다")
        if self.exact_mass <= 0.0:
            errors.append(f"정밀질량이 0 이하입니다: {self.exact_mass}")
        if self.count_min < 0:
            errors.append(f"최소값이 음수입니다: {self.count_min}")
        if self.count_max < self.count_min:
            errors.append(
                f"최소값({self.count_min})이 최대값({self.count_max})보다 큽니다"
            )
        return errors

    def __str__(self) -> str:
        return (
            f"  └─ {self.name} ({self.sub_type.value}): "
            f"{self.formula_or_mass} = {self.exact_mass:.4f} Da "
            f"× avg{self.count_avg:.1f} [{self.count_min}~{self.count_max}]"
        )


def parse_formula_or_mass(text: str, mass_calculator) -> tuple[str, float, float]:
    """
    사용자 입력 문자열을 분자식 또는 직접 질량으로 자동 판별한다.

    규칙:
        - 순수 숫자 (예: "44.026", "3850") → 정밀/평균 질량으로 직접 사용
        - 문자 포함 (예: "C2H4O", "H2O") → 분자식으로 파싱

    Returns:
        (formula_display, exact_mass, average_mass)
        formula_display: 표시용 문자열 ("(직접입력 44.0260 Da)" 또는 분자식)

    Raises:
        FormulaParseError: 분자식 파싱 실패
        ValueError: 빈 입력
    """
    text = text.strip()
    if not text:
        raise ValueError("입력값이 비어 있습니다")

    try:
        exact_mass = float(text)
        formula_display = f"~{exact_mass:.4f}Da"
        return formula_display, exact_mass, exact_mass
    except ValueError:
        # 분자식으로 파싱
        exact_mass = mass_calculator.calc_exact_mass(text)
        avg_mass = mass_calculator.calc_average_mass(text)
        return text, exact_mass, avg_mass


@dataclass
class Monomer:
    """
    단일 모노머(반복단위)의 정의.

    SRS §5.1 Monomer Table 컬럼:
        name        — 모노머 이름 (예: "EO", "LA", "HDI")
        monomer_type — 유형 (MonomerType enum)
        formula     — 분자식 또는 직접 입력 표시 문자열
        exact_mass  — 단일동위원소 정밀질량 (Da)
        min_count   — 솔버 탐색 최소값 (≥ 0)
        max_count   — 솔버 탐색 최대값 (> min_count)
        sub_items   — Block 유형일 때 하위 성분 목록
                      Block 질량 = Σ(sub_item 평균 질량)
    """

    name: str
    monomer_type: MonomerType
    formula: str
    exact_mass: float
    average_mass: float = 0.0
    min_count: int = 0
    max_count: int = 100
    sub_items: list[BlockSubItem] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Block 질량 계산
    # ------------------------------------------------------------------

    def compute_block_mass(self) -> float:
        """
        Block 유형일 때 하위 성분의 평균 질량 합을 반환한다.

        sub_items가 비어 있으면 exact_mass를 그대로 반환.
        """
        if self.monomer_type == MonomerType.BLOCK and self.sub_items:
            return sum(item.mass_contribution_avg for item in self.sub_items)
        return self.exact_mass

    def compute_block_average_mass(self) -> float:
        if self.monomer_type == MonomerType.BLOCK and self.sub_items:
            return sum(item.mass_contribution_average_mass for item in self.sub_items)
        return self.average_mass

    def effective_mass(self) -> float:
        """
        솔버에서 사용할 실효 질량 (Da).

        Block 유형이고 sub_items가 있으면 계산 질량 반환,
        그 외엔 exact_mass 반환.
        """
        if self.monomer_type == MonomerType.BLOCK and self.sub_items:
            return self.compute_block_mass()
        return self.exact_mass

    def effective_average_mass(self) -> float:
        if self.monomer_type == MonomerType.BLOCK and self.sub_items:
            return self.compute_block_average_mass()
        return self.average_mass

    def refresh_block_mass(self) -> None:
        """
        Block 유형일 때 sub_items에서 exact_mass를 재계산한다.
        하위 성분 추가/수정 후 호출한다.
        """
        if self.monomer_type == MonomerType.BLOCK:
            self.exact_mass = self.compute_block_mass()
            self.average_mass = self.compute_block_average_mass()

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_formula(
        cls,
        name: str,
        monomer_type: MonomerType,
        formula: str,
        mass_calculator,
        min_count: int = 0,
        max_count: int = 100,
    ) -> "Monomer":
        """
        분자식으로부터 Monomer 객체를 생성하고 정밀질량을 자동 계산한다.

        Args:
            name: 모노머 이름
            monomer_type: 유형
            formula: 분자식 문자열
            mass_calculator: MassCalculator 인스턴스
            min_count: 최소값
            max_count: 최대값

        Returns:
            Monomer 인스턴스 (exact_mass 자동 설정)
        """
        exact_mass = mass_calculator.calc_exact_mass(formula)
        try:
            average_mass = mass_calculator.calc_average_mass(formula)
        except Exception:
            average_mass = exact_mass

        return cls(
            name=name,
            monomer_type=monomer_type,
            formula=formula,
            exact_mass=exact_mass,
            average_mass=average_mass,
            min_count=min_count,
            max_count=max_count,
        )

    @classmethod
    def from_formula_or_mass(
        cls,
        name: str,
        monomer_type: MonomerType,
        formula_or_mass: str,
        mass_calculator,
        min_count: int = 0,
        max_count: int = 100,
        sub_items: list[BlockSubItem] | None = None,
    ) -> "Monomer":
        """
        분자식 또는 정밀질량 문자열로부터 Monomer를 생성한다.

        입력 판별 규칙:
            - 순수 숫자 (예: "3850.12") → 정밀질량 직접 사용
            - 문자 포함 (예: "C2H4O") → 분자식으로 파싱하여 자동 계산
            - Block 유형이고 sub_items 있음 → sub_items에서 질량 계산

        Args:
            name: 모노머 이름
            monomer_type: 유형
            formula_or_mass: 분자식 또는 질량 문자열
            mass_calculator: MassCalculator 인스턴스
            min_count: 최소값 (블록 개수)
            max_count: 최대값 (블록 개수)
            sub_items: Block 하위 성분 목록 (Block 유형 시 사용)

        Returns:
            Monomer 인스턴스
        """
        if sub_items is None:
            sub_items = []

        # Block + sub_items: 하위 성분에서 질량 계산
        if monomer_type == MonomerType.BLOCK and sub_items:
            exact_mass = sum(item.mass_contribution_avg for item in sub_items)
            average_mass = sum(item.mass_contribution_average_mass for item in sub_items)
            formula = "~block"
        else:
            formula, exact_mass, average_mass = parse_formula_or_mass(formula_or_mass, mass_calculator)

        return cls(
            name=name,
            monomer_type=monomer_type,
            formula=formula,
            exact_mass=exact_mass,
            average_mass=average_mass,
            min_count=min_count,
            max_count=max_count,
            sub_items=sub_items,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """
        모노머 정의의 유효성을 검사한다.

        Returns:
            오류 메시지 리스트. 빈 리스트 = 정상.
        """
        errors: list[str] = []

        if not self.name or not self.name.strip():
            errors.append("모노머 이름이 비어 있습니다")

        if self.monomer_type != MonomerType.BLOCK:
            if self.exact_mass <= 0.0:
                errors.append(f"정밀질량이 0 이하입니다: {self.exact_mass}")

        if self.min_count < 0:
            errors.append(f"최소값이 음수입니다: {self.min_count}")

        if self.max_count <= 0:
            errors.append(f"최대값이 0 이하입니다: {self.max_count}")

        if self.min_count > self.max_count:
            errors.append(
                f"최소값({self.min_count})이 최대값({self.max_count})보다 큽니다"
            )

        # Block 유형: 하위 성분도 검사
        for sub in self.sub_items:
            sub_errors = sub.validate()
            for e in sub_errors:
                errors.append(f"  [{sub.name}] {e}")

        return errors

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        mass_str = (
            f"{self.effective_mass():.4f} Da (블록)"
            if self.monomer_type == MonomerType.BLOCK
            else f"{self.exact_mass:.6f} Da"
        )
        result = (
            f"{self.name} ({self.monomer_type.value}): "
            f"{self.formula} = {mass_str} "
            f"[{self.min_count}~{self.max_count}]"
        )
        for sub in self.sub_items:
            result += f"\n{sub}"
        return result

    def search_range(self) -> range:
        """솔버 탐색 범위를 range 객체로 반환한다."""
        return range(self.min_count, self.max_count + 1)

    def candidate_count(self) -> int:
        """탐색 가능한 후보 수 (max - min + 1)."""
        return self.max_count - self.min_count + 1
