"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Periodic Series Detection & Composition Family Scoring

1. 반복단위 질량 M_r 간격으로 이어지는 피크 시리즈 검출
2. 미지 반복 간격 탐색 (피크 쌍 질량차 히스토그램)
3. Kendrick Mass Defect
4. 솔버 결과의 조성 계열(family) 점수화:
   시리즈에서 연속한 피크의 참 조성은 반복단위 A 하나씩만 증가하고 나머지
   (다른 모노머 수, 어덕트, 동위원소 오프셋)는 같다. 이 규칙으로 후보를 묶어
   많은 피크를 연속적으로, 작은 오차로 설명하는 계열일수록 높은 점수를 준다.
"""

from __future__ import annotations

from mpcs.core.i18n import tr
import math
from dataclasses import dataclass, field

import numpy as np

from mpcs.models.result import RankedResultSet


# ---------------------------------------------------------------------------
# 1. 시리즈 검출
# ---------------------------------------------------------------------------

@dataclass
class PeakSeries:
    series_id: int
    repeat_name: str
    repeat_mass: float
    peak_indices: list[int]          # m/z 오름차순 피크 인덱스

    def label(self) -> str:
        return tr('S{series_id} ({repeat_name}, {v}개)', series_id=self.series_id, repeat_name=self.repeat_name, v=len(self.peak_indices))


def detect_series(
    mz: np.ndarray,
    repeats: dict[str, float],
    tol: float,
    min_length: int = 4,
    max_gap: int = 1,
) -> list[PeakSeries]:
    """
    각 반복단위 질량에 대해, Δm ≈ k·M_r (k = 1..max_gap+1, ±tol)로 이어지는 피크를
    union-find로 연결해 길이 min_length 이상인 시리즈를 반환한다.

    Args:
        mz:       피크 m/z 배열 (오름차순)
        repeats:  {반복단위 이름: 질량}
        tol:      허용 오차 (Da)
    """
    mz = np.asarray(mz, dtype=float)
    out: list[PeakSeries] = []
    sid = 1
    for name, mass in repeats.items():
        if mass <= 0:
            continue
        parent = list(range(mz.size))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(mz.size):
            for k in range(1, max_gap + 2):
                target = mz[i] + k * mass
                lo = np.searchsorted(mz, target - tol, side="left")
                hi = np.searchsorted(mz, target + tol, side="right")
                if hi > lo:
                    j = lo + int(np.argmin(np.abs(mz[lo:hi] - target)))
                    parent[find(j)] = find(i)
                    break
        groups: dict[int, list[int]] = {}
        for i in range(mz.size):
            groups.setdefault(find(i), []).append(i)
        for members in sorted(groups.values(), key=lambda g: -len(g)):
            if len(members) >= min_length:
                out.append(PeakSeries(sid, name, mass, sorted(members)))
                sid += 1
    return out


def find_spacings(mz: np.ndarray, intensity: np.ndarray | None = None, max_delta: float = 300.0,
                  bin_da: float = 0.02, top_n_peaks: int = 200, top: int = 5) -> list[tuple[float, int]]:
    """강한 피크 쌍의 질량차 히스토그램에서 우세한 반복 간격을 찾는다."""
    mz = np.asarray(mz, dtype=float)
    if mz.size < 3:
        return []
    if intensity is not None and mz.size > top_n_peaks:
        idx = np.argsort(-np.asarray(intensity))[:top_n_peaks]
        mz = np.sort(mz[idx])
    d = (mz[None, :] - mz[:, None])
    d = d[(d > 10.0) & (d <= max_delta)]
    if d.size == 0:
        return []
    bins = np.round(d / bin_da).astype(np.int64)
    vals, counts = np.unique(bins, return_counts=True)
    # 인접 bin 합산 (bin 경계에 걸친 값 보정)
    order = np.argsort(-counts)[: top * 10]
    cands = []
    for o in order:
        near = np.abs(vals - vals[o]) <= 1
        cands.append((float(np.average(vals[near], weights=counts[near]) * bin_da), int(counts[near].sum())))

    def is_multiple(d: float, base: float) -> bool:
        k = round(d / base)
        return k >= 2 and abs(d - k * base) < 3 * bin_da * k

    # 다른 후보의 정수배(예: 3×EO = 132.08)는 기본 간격이 아니므로 제외
    result: list[tuple[float, int]] = []
    for d, n in sorted(cands, key=lambda x: -x[1]):
        if any(abs(d - r) < 3 * bin_da for r, _ in result):
            continue
        # 기본 간격 후보는 충분히 강해야 함 (약한 노이즈 간격의 정수배로 오인 방지)
        if any(is_multiple(d, base) for base, nb in cands if base < d and nb >= 0.5 * n):
            continue
        result.append((d, n))
        if len(result) >= top:
            break
    return result


def kendrick_mass_defect(mz: np.ndarray, repeat_mass: float) -> np.ndarray:
    """KMD = round(KM) − KM,  KM = m · round(M_r)/M_r. 같은 시리즈는 같은 KMD를 갖는다."""
    km = np.asarray(mz, dtype=float) * round(repeat_mass) / repeat_mass
    return np.round(km) - km


# ---------------------------------------------------------------------------
# 2. 조성 계열 점수화
# ---------------------------------------------------------------------------

@dataclass
class CompositionFamily:
    family_id: int
    repeat_name: str
    fixed: tuple[tuple[str, int], ...]           # 반복단위를 제외한 나머지 조성
    adduct_label: str
    isotope_offset: int
    members: list[tuple[int, int, float, int]] = field(default_factory=list)  # (peak, n, err, cand)
    run_length: int = 0
    score: float = 0.0
    mean_probability: float = 0.0

    @property
    def support(self) -> int:
        return len(self.members)

    @property
    def n_range(self) -> tuple[int, int]:
        ns = [m[1] for m in self.members]
        return (min(ns), max(ns)) if ns else (0, 0)

    @property
    def mean_abs_error(self) -> float:
        return float(np.mean([m[2] for m in self.members])) if self.members else 0.0

    def label(self) -> str:
        lo, hi = self.n_range
        fixed = " ".join(f"{k}{v}" for k, v in self.fixed if v > 0) or "—"
        iso = f" (+{self.isotope_offset} iso)" if self.isotope_offset else ""
        return f"{self.repeat_name} n={lo}–{hi} · {fixed} · {self.adduct_label}{iso}"


def score_families(
    result_sets: list[RankedResultSet],
    repeat_names: list[str],
    tolerance_da: float,
    null_score: float = 1.0,
) -> list[CompositionFamily]:
    """
    후보를 조성 계열로 묶어 점수를 매기고, 각 후보의 probability/family 정보를 채운다.

    점수 = Σ_members w(err) × (1 if 최장 연속 구간 소속 else 0.5)
           w(err) = exp(−½ (err/σ)²),  σ = tol/2
    피크별 확률 = softmax(후보의 최고 계열 점수) — '설명되지 않음' 가상 후보(null_score) 포함

    Args:
        result_sets:   피크 순서대로의 솔버 결과 (in-place로 probability 등 갱신)
        repeat_names:  계열 축으로 쓸 반복단위 이름 (일반 모노머)
        tolerance_da:  솔버 허용 오차

    Returns:
        점수 내림차순 계열 목록 (설명 피크 2개 이상)
    """
    sigma = max(tolerance_da / 2.0, 1e-9)
    buckets: dict[tuple, dict[int, tuple[int, float, int]]] = {}

    for p, rs in enumerate(result_sets):
        for c, r in enumerate(rs.results):
            counts = r.composition.counts
            for a in repeat_names:
                n = None
                rest = []
                for k, v in counts:
                    if k == a:
                        n = v
                    else:
                        rest.append((k, v))
                if n is None or n <= 0:
                    continue
                key = (a, tuple(rest), r.adduct_label, r.isotope_offset)
                peaks = buckets.setdefault(key, {})
                prev = peaks.get(p)
                if prev is None or r.error_da < prev[1]:
                    peaks[p] = (n, r.error_da, c)

    families: list[CompositionFamily] = []
    cand_best: dict[tuple[int, int], tuple[float, int, int]] = {}  # (p,c) → (score, fid, support)
    for key, peaks in buckets.items():
        a, rest, adduct, iso = key
        members = sorted(((p, n, e, c) for p, (n, e, c) in peaks.items()), key=lambda m: m[1])
        ns = [m[1] for m in members]
        best_run = (0, 0)
        start = 0
        for i in range(1, len(ns) + 1):
            if i == len(ns) or ns[i] != ns[i - 1] + 1:
                if i - start > best_run[1] - best_run[0]:
                    best_run = (start, i)
                start = i
        in_run = set(range(*best_run))
        score = sum(math.exp(-0.5 * (m[2] / sigma) ** 2) * (1.0 if i in in_run else 0.5)
                    for i, m in enumerate(members))
        fam = CompositionFamily(
            family_id=len(families) + 1, repeat_name=a, fixed=rest, adduct_label=adduct,
            isotope_offset=iso, members=members, run_length=best_run[1] - best_run[0], score=score,
        )
        families.append(fam)
        for p, _n, _e, c in members:
            cur = cand_best.get((p, c))
            if cur is None or score > cur[0]:
                cand_best[(p, c)] = (score, fam.family_id, len(members))

    # 피크별 softmax
    for p, rs in enumerate(result_sets):
        scores = [cand_best.get((p, c), (0.0, None, 1))[0] for c in range(len(rs.results))]
        if not scores:
            continue
        mx = max(max(scores), null_score)
        exps = [math.exp(s - mx) for s in scores]
        z = sum(exps) + math.exp(null_score - mx)
        for c, r in enumerate(rs.results):
            s, fid, sup = cand_best.get((p, c), (0.0, None, 1))
            r.probability = exps[c] / z
            r.family_id = fid
            r.family_support = sup

    prob_of = {(p, c): r.probability for p, rs in enumerate(result_sets) for c, r in enumerate(rs.results)}
    out = [f for f in families if f.support >= 2]
    for f in out:
        f.mean_probability = float(np.mean([prob_of.get((m[0], m[3]), 0.0) for m in f.members]))
    out.sort(key=lambda f: (-f.score, f.mean_abs_error))
    for i, f in enumerate(out, start=1):
        old = f.family_id
        f.family_id = i
        for p, _n, _e, c in f.members:
            r = result_sets[p].results[c]
            if r.family_id == old:
                r.family_id = -i   # 임시 표시 (아래에서 양수화)
    for rs in result_sets:
        for r in rs.results:
            if r.family_id is not None:
                r.family_id = -r.family_id if r.family_id < 0 else None
    # 각 피크의 후보를 확률 내림차순으로 재정렬 (동률이면 오차 순)
    for rs in result_sets:
        rs.results.sort(key=lambda r: (-(r.probability or 0.0), r.error_da))
    return out
