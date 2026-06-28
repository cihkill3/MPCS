"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Peak Data, SEC Data, Result
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# PeakData  (SRS §12 MALDI Data Input)
# ---------------------------------------------------------------------------

@dataclass
class PeakData:
    """
    MALDI 피크 데이터.

    SRS §12 MALDI Data Input:
        §12.1 단일 피크 입력
        §12.2 다중 피크 입력
        §12.4 필수 컬럼: m/z, Intensity

    Attributes:
        mz_values:   m/z 값 리스트 (Da)
        intensities: 상대 강도 리스트 (mz_values와 길이 동일)

    사용 예:
        # 단일 피크
        pd = PeakData.single(15123.43)
        # 다중 피크
        pd = PeakData(mz_values=[1000.0, 1044.0], intensities=[100.0, 80.0])
    """

    mz_values: list[float] = field(default_factory=list)
    intensities: list[float] = field(default_factory=list)

    @classmethod
    def single(cls, mz: float, intensity: float = 100.0) -> "PeakData":
        """단일 m/z 값으로 PeakData를 생성한다."""
        return cls(mz_values=[mz], intensities=[intensity])

    def is_empty(self) -> bool:
        """피크 데이터가 비어 있는지 확인한다."""
        return len(self.mz_values) == 0

    def peak_count(self) -> int:
        """피크 수를 반환한다."""
        return len(self.mz_values)

    def validate(self) -> list[str]:
        """피크 데이터 유효성 검사."""
        errors: list[str] = []

        if len(self.mz_values) != len(self.intensities):
            errors.append(
                f"m/z 수({len(self.mz_values)})와 "
                f"강도 수({len(self.intensities)})가 일치하지 않습니다"
            )

        for i, mz in enumerate(self.mz_values):
            if mz <= 0.0:
                errors.append(f"피크 {i+1}: m/z 값이 0 이하입니다 ({mz})")

        return errors


# ---------------------------------------------------------------------------
# SECData  (SRS §17 SEC Data Integration)
# ---------------------------------------------------------------------------

@dataclass
class SECData:
    """
    SEC(Size Exclusion Chromatography) 데이터.

    SRS §17 SEC Data Integration:
        §17.1 Inputs: Mn, Mw, PDI
        §17.2 Filtering: MW 범위로 후보 조성 필터링

    Attributes:
        mn:  수평균 분자량 (Da)
        mw:  중량평균 분자량 (Da)
        pdi: 다분산 지수 (= Mw/Mn)
    """

    mn: float
    mw: float
    pdi: float

    def contains(self, molecular_weight: float) -> bool:
        """
        주어진 분자량이 Mn~Mw 범위 내에 있는지 확인한다.

        SRS §17.2 Filtering.

        Args:
            molecular_weight: 확인할 분자량 (Da)

        Returns:
            True: Mn ≤ MW ≤ Mw
        """
        return self.mn <= molecular_weight <= self.mw

    def validate(self) -> list[str]:
        """SEC 데이터 유효성 검사."""
        errors: list[str] = []

        if self.mn <= 0.0:
            errors.append(f"Mn이 0 이하입니다: {self.mn}")
        if self.mw <= 0.0:
            errors.append(f"Mw가 0 이하입니다: {self.mw}")
        if self.mn > self.mw:
            errors.append(f"Mn({self.mn})이 Mw({self.mw})보다 큽니다")
        if self.pdi < 1.0:
            errors.append(f"PDI가 1.0 미만입니다: {self.pdi}")

        # PDI 일관성 검사 (허용 오차 1%)
        if self.mn > 0 and abs(self.pdi - self.mw / self.mn) > 0.01:
            errors.append(
                f"PDI({self.pdi:.4f})가 Mw/Mn({self.mw/self.mn:.4f})과 "
                f"일치하지 않습니다 (허용오차 1%)"
            )

        return errors


# ---------------------------------------------------------------------------
# Composition & Result  (SRS §18 Results Module)
# ---------------------------------------------------------------------------

@dataclass(init=False, frozen=True)
class Composition:
    """
    고분자 조성 (불변 객체 — 딕셔너리 키로 사용 가능).

    SRS §18 Results Module.

    Attributes:
        counts: {모노머_이름: 반복_단위_수} 불변 매핑

    사용 예:
        c = Composition(counts={"EO": 90, "LA": 52, "HDI": 11})
        key = hash(c)  # frozenset 기반 해시

    Note:
        frozen=True이므로 생성 후 수정 불가.
        딕셔너리 키 또는 set 원소로 안전하게 사용 가능.
    """

    counts: tuple[tuple[str, int], ...]  # (name, count) 정렬된 튜플

    def __init__(self, counts: dict[str, int] | tuple[tuple[str, int], ...]) -> None:
        """dict 또는 정렬된 tuple로 초기화를 지원한다."""
        if isinstance(counts, dict):
            sorted_counts = tuple(sorted(counts.items()))
        else:
            sorted_counts = tuple(sorted(counts))
        object.__setattr__(self, "counts", sorted_counts)

    def to_dict(self) -> dict[str, int]:
        """원소 카운트를 딕셔너리로 반환한다."""
        return dict(self.counts)

    def get(self, monomer_name: str, default: int = 0) -> int:
        """특정 모노머의 반복 단위 수를 반환한다."""
        return dict(self.counts).get(monomer_name, default)

    def total_units(self) -> int:
        """전체 반복 단위 수 합계."""
        return sum(c for _, c in self.counts)

    def to_string(self) -> str:
        """
        인간이 읽기 쉬운 형식으로 변환한다.
        예: "EO×90 + LA×52 + HDI×11"
        """
        parts = [f"{name}×{count}" for name, count in self.counts if count > 0]
        return " + ".join(parts) if parts else "(empty)"

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"Composition({dict(self.counts)!r})"


# SRS §18 결과 출력 최대 개수 (Q8: 오차 적은 순 상위 100개)
MAX_RESULTS: Final[int] = 100


@dataclass
class SolverResult:
    """
    단일 후보 조성에 대한 솔버 결과.

    SRS §18.1 Results Table:
        Rank, Calculated Mass, Observed Mass, Error, Probability, Composition

    SRS §18.2 Detailed Result View:
        Composition, Repeat counts, Calculated mass, Observed mass, Error, Probability

    Q7: ppm 오차 표시 제외 (Da 단위만 사용)
    Q11: probability=None 시 GUI에서 '-'로 표시
    """

    composition: Composition
    calculated_mass: float        # 이론 m/z (Da)  SRS §18
    observed_mass: float          # 관측 m/z (Da)
    error_da: float               # |observed - calculated| (Da)  SRS §13.3
    adduct_label: str = ""        # 사용된 어덕트 레이블
    probability: float | None = None  # 몬테카를로 확률 (미실행 시 None → GUI '-')
    isotope_offset: int = 0       # 0이면 모노이소토픽 매칭, N이면 N번째 동위원소 매칭
    formula: str | None = None    # 이온화된 전체 분자식 (직접 질량 입력 포함 시 None)

    @property
    def probability_display(self) -> str:
        """
        결과 테이블에 표시할 확률 문자열.
        Q11: 몬테카를로 미실행 시 '-'
        """
        if self.probability is None:
            return "-"
        return f"{self.probability * 100:.2f}%"

    def __str__(self) -> str:
        return (
            f"{self.composition.to_string()} | "
            f"calc={self.calculated_mass:.4f} obs={self.observed_mass:.4f} "
            f"err={self.error_da:.4f} Da"
        )


@dataclass
class RankedResultSet:
    """
    단일 관측 피크에 대한 정렬된 솔버 결과 집합.

    SRS §13.4 Ranking: 오차(error_da) 기준 오름차순 정렬.
    Q8: 최대 MAX_RESULTS(100)개까지 저장.

    Attributes:
        peak_mz: 원본 관측 m/z
        results: SolverResult 리스트 (error_da 오름차순, 최대 100개)
    """

    peak_mz: float
    results: list[SolverResult] = field(default_factory=list)

    def best(self) -> SolverResult | None:
        """오차가 가장 작은 결과를 반환한다."""
        return self.results[0] if self.results else None

    def count(self) -> int:
        """후보 수를 반환한다."""
        return len(self.results)

    def is_empty(self) -> bool:
        """결과가 없는지 확인한다."""
        return len(self.results) == 0
