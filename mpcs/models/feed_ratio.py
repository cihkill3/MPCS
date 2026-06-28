"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Feed Ratio Definition

SRS §9 Feed Ratio Module:
    §9.1 Feed Table: Component, mmol
    §9.2 Automatic Ratio Calculation
    §9.3 Tolerance: 사용자 정의 허용오차 (예: ±20%)
    §9.4 Solver Filtering: 공급비 제약을 솔버에 적용

⚠️ ASSUMPTION (Q4 — 사전분석 보고서 참조):
    Feed Component 이름과 Monomer Table의 Name이 동일하다고 가정한다.
    즉, Feed Table의 Component는 Monomer Table의 Name과 1:1 매핑.
    (예: Component="EO" → Monomer(name="EO"))
    블록 단위 참조(예: "PLA-PEG-PLA")는 단일 Monomer Name으로 매핑.
    TODO: Q4 답변 후 매핑 로직 수정 가능성 있음.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


_DEFAULT_TOLERANCE_PCT: Final[float] = 20.0  # SRS §9.3 예시값


@dataclass
class FeedRatioEntry:
    """
    공급비 테이블의 단일 행.

    SRS §9.1 Feed Table:
        Component  — 성분 이름 (Monomer Table의 Name과 매핑)
        mmol       — 투입량 (밀리몰)
    """

    component_name: str
    mmol: float

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.component_name or not self.component_name.strip():
            errors.append("성분 이름이 비어 있습니다")
        if self.mmol <= 0.0:
            errors.append(f"mmol 값이 0 이하입니다: {self.mmol}")
        return errors


@dataclass
class FeedRatio:
    """
    공급비 전체 정의.

    SRS §9 Feed Ratio Module 준수.

    Attributes:
        entries:       FeedRatioEntry 리스트
        tolerance_pct: 허용 오차 (%) — 예: 20.0 → ±20%

    사용 예:
        fr = FeedRatio(
            entries=[
                FeedRatioEntry("PLA", 1.0),
                FeedRatioEntry("SMA", 4.976),
                FeedRatioEntry("HDI", 5.042),
            ],
            tolerance_pct=20.0,
        )
        ratios = fr.calc_ratios()
        # {"PLA": 1.0, "SMA": 4.976, "HDI": 5.042}  (PLA 기준 정규화)
    """

    entries: list[FeedRatioEntry] = field(default_factory=list)
    tolerance_pct: float = _DEFAULT_TOLERANCE_PCT

    # ------------------------------------------------------------------
    # Ratio calculation (SRS §9.2)
    # ------------------------------------------------------------------

    def calc_ratios(self) -> dict[str, float]:
        """
        각 성분의 공급 몰비를 계산한다.

        SRS §9.2: 자동으로 비율 계산.
        가장 작은 mmol 값을 1로 정규화한다.

        Returns:
            {component_name: 정규화_몰비} 딕셔너리.
            entries가 비어 있으면 빈 딕셔너리 반환.
        """
        if not self.entries:
            return {}

        min_mmol = min(e.mmol for e in self.entries if e.mmol > 0)
        if min_mmol == 0:
            return {}

        return {
            entry.component_name: entry.mmol / min_mmol
            for entry in self.entries
        }

    def check_composition(
        self,
        composition: dict[str, int],
    ) -> bool:
        """
        주어진 조성이 공급비 허용 범위 내에 있는지 확인한다.

        SRS §9.4 Solver Filtering.

        Q4 가정:
        - composition의 키가 FeedRatioEntry.component_name과 1:1 매핑.
        - 공급비 비율과 조성 내 반복단위 수의 비율을 비교.
        - 매핑 없는 성분은 검사하지 않는다.

        Args:
            composition: {monomer_name: repeat_count}

        Returns:
            True: 허용 범위 내 / False: 허용 범위 초과
        """
        ratios = self.calc_ratios()
        if len(ratios) < 2:
            # 성분이 1개 이하이면 비율 비교 불가 → 통과
            return True

        # 기준 성분: 가장 작은 mmol (ratio=1.0)
        ref_name = min(self.entries, key=lambda e: e.mmol).component_name
        ref_count = composition.get(ref_name, 0)

        if ref_count == 0:
            # 기준 성분이 0이면 비율 정의 불가 → 필터링 통과로 처리
            return True

        tol_factor = self.tolerance_pct / 100.0

        for comp_name, target_ratio in ratios.items():
            if comp_name == ref_name:
                continue
            actual_count = composition.get(comp_name, 0)
            actual_ratio = actual_count / ref_count
            lower = target_ratio * (1.0 - tol_factor)
            upper = target_ratio * (1.0 + tol_factor)
            if not (lower <= actual_ratio <= upper):
                return False

        return True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """공급비 정의 유효성 검사."""
        errors: list[str] = []

        if not self.entries:
            errors.append("공급비 항목이 없습니다")
            return errors

        for i, entry in enumerate(self.entries):
            for msg in entry.validate():
                errors.append(f"항목 {i+1}: {msg}")

        # 중복 성분 이름 검사
        names = [e.component_name for e in self.entries]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            errors.append(f"중복된 성분 이름: {', '.join(sorted(duplicates))}")

        if self.tolerance_pct < 0.0 or self.tolerance_pct > 100.0:
            errors.append(
                f"허용 오차가 유효 범위(0~100%)를 벗어났습니다: {self.tolerance_pct}%"
            )

        return errors
