"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Project (최상위 상태 컨테이너)

SRS §4.2 Project Section:
    Project Name, Monomer Count
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from mpcs.models.adduct import Adduct, make_default_adducts
from mpcs.models.constraint import Constraint
from mpcs.models.end_group import EndGroup
from mpcs.models.feed_ratio import FeedRatio
from mpcs.models.monomer import Monomer
from mpcs.models.result import PeakData, SECData


@dataclass
class Project:
    """
    MPCS 프로젝트 — 모든 입력 상태의 최상위 컨테이너.

    SRS §4.2 Project Section 준수.

    Attributes:
        name:               프로젝트 이름
        monomers:           모노머 정의 목록 (SRS §5)
        constraints:        제약식 목록 (SRS §8)
        feed_ratio:         공급비 (SRS §9)
        end_group:          말단기 (SRS §10)
        adducts:            어덕트 목록 (SRS §11)
        peak_data:          MALDI 피크 데이터 (SRS §12)
        sec_data:           SEC 데이터 (SRS §17, 선택)
        average_block_mode: Average Block Mode 활성화 여부 (SRS §7)
        created_at:         생성 시각 (ISO 8601)
        modified_at:        수정 시각 (ISO 8601)
    """

    name: str = "새 프로젝트"
    monomers: list[Monomer] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    feed_ratio: FeedRatio = field(default_factory=FeedRatio)
    end_group: EndGroup = field(default_factory=EndGroup)
    adducts: list[Adduct] = field(default_factory=make_default_adducts)
    peak_data: PeakData = field(default_factory=PeakData)
    sec_data: SECData | None = None
    average_block_mode: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def touch(self) -> None:
        """수정 시각을 현재 시각으로 업데이트한다."""
        self.modified_at = datetime.now().isoformat()

    def active_constraints(self) -> list[Constraint]:
        """활성화된 제약식만 반환한다."""
        return [c for c in self.constraints if c.is_active]

    def enabled_adducts(self) -> list[Adduct]:
        """활성화된 어덕트만 반환한다."""
        return [a for a in self.adducts if a.enabled]

    def monomer_names(self) -> list[str]:
        """모노머 이름 목록을 반환한다."""
        return [m.name for m in self.monomers]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """프로젝트 전체 유효성 검사."""
        errors: list[str] = []

        if not self.name or not self.name.strip():
            errors.append("프로젝트 이름이 비어 있습니다")

        if not self.monomers:
            errors.append("모노머가 하나도 정의되지 않았습니다")

        # 모노머 중복 이름 검사
        names = [m.name for m in self.monomers]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            errors.append(f"중복된 모노머 이름: {', '.join(sorted(duplicates))}")

        for monomer in self.monomers:
            for msg in monomer.validate():
                errors.append(f"모노머 '{monomer.name}': {msg}")

        for i, constraint in enumerate(self.constraints):
            for msg in constraint.validate():
                errors.append(f"제약식 {i+1}: {msg}")

        for msg in self.end_group.validate():
            errors.append(f"말단기: {msg}")

        if not self.enabled_adducts():
            errors.append("활성화된 어덕트가 없습니다. 최소 하나 이상 선택하십시오.")

        if not self.peak_data.is_empty():
            for msg in self.peak_data.validate():
                errors.append(f"MALDI 데이터: {msg}")

        if self.sec_data is not None:
            for msg in self.sec_data.validate():
                errors.append(f"SEC 데이터: {msg}")

        return errors

    def __str__(self) -> str:
        return (
            f"Project '{self.name}': "
            f"{len(self.monomers)}개 모노머, "
            f"{len(self.constraints)}개 제약식, "
            f"{self.peak_data.peak_count()}개 피크"
        )
