"""
MPCS — MALDI Polymer Composition Solver
Models Layer: Spectrum / Picked Peak

원본 질량 스펙트럼(MALDI 단일 스캔 또는 LC-MS 다중 스캔)과 피크 검출 결과.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Spectrum:
    """
    단일 스캔 스펙트럼.

    Attributes:
        mz, intensity: 동일 길이 1차원 배열 (m/z 오름차순)
        centroided:    True면 이미 센트로이드된 막대 스펙트럼 (LC-MS에서 흔함)
        scan_num:      mzXML scan num
        ms_level:      MS 레벨 (1 = MS1)
        rt_sec:        머무름 시간 (초), 없으면 None
        polarity:      '+' / '-' / None
    """

    mz: np.ndarray
    intensity: np.ndarray
    centroided: bool = False
    scan_num: int | None = None
    ms_level: int = 1
    rt_sec: float | None = None
    polarity: str | None = None

    def __post_init__(self) -> None:
        self.mz = np.asarray(self.mz, dtype=float)
        self.intensity = np.asarray(self.intensity, dtype=float)
        if self.mz.size > 1 and np.any(np.diff(self.mz) < 0):
            order = np.argsort(self.mz, kind="stable")
            self.mz, self.intensity = self.mz[order], self.intensity[order]

    @property
    def size(self) -> int:
        return int(self.mz.size)

    def label(self) -> str:
        parts = [f"scan {self.scan_num}" if self.scan_num is not None else "scan"]
        parts.append(f"MS{self.ms_level}")
        if self.rt_sec is not None:
            parts.append(f"RT {self.rt_sec / 60:.2f} min")
        parts.append(f"{self.size:,} pts")
        if self.centroided:
            parts.append("centroid")
        return " · ".join(parts)


@dataclass
class SpectrumFile:
    """mzXML 등 스펙트럼 파일 전체 (스캔 목록)."""

    path: str
    scans: list[Spectrum] = field(default_factory=list)

    def ms1_scans(self) -> list[Spectrum]:
        return [s for s in self.scans if s.ms_level == 1] or list(self.scans)

    def combine(self, scans: list[Spectrum]) -> Spectrum:
        """
        여러 스캔을 합산한다 (LC-MS 머무름 시간 구간 합산용).

        프로파일: 점 수가 가장 많은 스캔의 m/z 격자로 선형 보간 후 합산
        센트로이드: 막대를 모두 모은 뒤 m/z 정렬
        """
        if not scans:
            raise ValueError("합산할 스캔이 없습니다")
        if len(scans) == 1:
            return scans[0]
        if all(s.centroided for s in scans):
            mz = np.concatenate([s.mz for s in scans])
            it = np.concatenate([s.intensity for s in scans])
            return Spectrum(mz, it, centroided=True, ms_level=scans[0].ms_level,
                            polarity=scans[0].polarity)
        ref = max(scans, key=lambda s: s.size)
        total = np.zeros_like(ref.intensity)
        for s in scans:
            if s.size:
                total += np.interp(ref.mz, s.mz, s.intensity, left=0.0, right=0.0)
        rts = [s.rt_sec for s in scans if s.rt_sec is not None]
        return Spectrum(ref.mz.copy(), total, centroided=False, ms_level=ref.ms_level,
                        rt_sec=float(np.mean(rts)) if rts else None, polarity=ref.polarity)


@dataclass
class PickedPeak:
    """피크 검출 결과 1개."""

    mz: float
    intensity: float
    snr: float = 0.0
    isotope_cluster_size: int = 1
