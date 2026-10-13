"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Synthetic Polymer Spectrum Generator

정답 조성을 알고 있는 합성 MALDI 스펙트럼을 만든다 (테스트·데모용).
    - 계열별 반복수 n 분포(가우시안 포락선)
    - molmass 동위원소 분포
    - 분해능 R에 따른 가우시안 피크 형태 (Reflectron ≈ 10,000 / Linear ≈ 500)
    - 지수 감쇠 베이스라인 + 가우시안 노이즈
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mpcs.core.atomic_mass_db import ELECTRON_MASS
from mpcs.core.formula_parser import FormulaParser
from mpcs.models.spectrum import Spectrum


@dataclass
class SeriesSpec:
    """
    합성할 고분자 계열 1개.

    repeat_formula: 반복단위 분자식 (예: "C2H4O")
    fixed_formula:  반복단위 외 전체 (말단기 + 고정 모노머 + 양이온 원자, 예: "H2O" + "C3H4O2"×5 + "Na")
    n_center/n_width: 반복수 분포 (가우시안)
    """

    repeat_formula: str
    fixed_formula: str
    n_min: int
    n_max: int
    n_center: float
    n_width: float
    weight: float = 1.0
    charge: int = 1


def _hill(elements: dict[str, int]) -> str:
    order = [e for e in ("C", "H") if e in elements] + sorted(e for e in elements if e not in ("C", "H"))
    return "".join(f"{e}{elements[e] if elements[e] > 1 else ''}" for e in order if elements[e] > 0)


def series_sticks(spec: SeriesSpec, min_rel: float = 0.001) -> list[tuple[float, float, int]]:
    """계열의 (m/z, 강도, n) 동위원소 막대 목록."""
    import molmass

    parser = FormulaParser()
    rep = parser.parse(spec.repeat_formula)
    fixed = parser.parse(spec.fixed_formula)
    sticks = []
    for n in range(spec.n_min, spec.n_max + 1):
        env = spec.weight * np.exp(-0.5 * ((n - spec.n_center) / spec.n_width) ** 2)
        if env < 1e-3:
            continue
        el = dict(fixed)
        for e, c in rep.items():
            el[e] = el.get(e, 0) + c * n
        dist = molmass.Formula(_hill(el)).spectrum()
        top = max(v.intensity for v in dist.values())
        for v in dist.values():
            if v.intensity / top >= min_rel:
                mz = (v.mass - spec.charge * ELECTRON_MASS) / spec.charge
                sticks.append((mz, env * v.intensity / top, n))
    return sticks


def make_polymer_spectrum(
    series: list[SeriesSpec],
    mz_min: float,
    mz_max: float,
    resolution: float = 10000.0,
    points_per_fwhm: float = 8.0,
    noise: float = 0.004,
    baseline: float = 0.03,
    seed: int = 0,
) -> Spectrum:
    """프로파일 스펙트럼을 합성한다 (최대 강도 ≈ 1)."""
    rng = np.random.default_rng(seed)
    step = (mz_min / resolution) / points_per_fwhm
    mz = np.arange(mz_min, mz_max, step)
    y = np.zeros_like(mz)
    for s in series:
        for smz, inten, _n in series_sticks(s):
            if not (mz_min - 20 <= smz <= mz_max + 20):
                continue
            sigma = smz / resolution / 2.3548
            lo = np.searchsorted(mz, smz - 5 * sigma)
            hi = np.searchsorted(mz, smz + 5 * sigma)
            y[lo:hi] += inten * np.exp(-0.5 * ((mz[lo:hi] - smz) / sigma) ** 2)
    if y.max() > 0:
        y /= y.max()
    y += baseline * np.exp(-(mz - mz_min) / (0.3 * (mz_max - mz_min)))
    y += rng.normal(0.0, noise, size=y.size)
    return Spectrum(mz, np.clip(y, 0, None) * 1e5)
