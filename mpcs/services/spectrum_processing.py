"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Spectrum Processing (Peak Picking)

원본 스펙트럼 → 피크 목록. NumPy만 사용.

프로파일 스펙트럼:
    1. m/z 범위 제한
    2. 베이스라인 제거 (블록 최소값 보간 + 이동평균)
    3. Savitzky–Golay 스무딩
    4. 노이즈 σ = 1.4826·MAD(1차 차분)/√2   (피크에 강건)
    5. 국소 최대 + S/N 임계값
    6. 최소 간격 억제 (강한 피크 우선)
    7. 반치폭 구간 가중 센트로이드
    8. (선택) 동위원소 클러스터 정리: 모노이소토픽(첫 피크) 또는 최대 피크만 유지
센트로이드 스펙트럼(LC-MS): 2, 3, 7단계 생략.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mpcs.models.spectrum import PickedPeak, Spectrum

ISOTOPE_SPACING = 1.00335


@dataclass
class PeakPickingParams:
    mz_min: float | None = None
    mz_max: float | None = None
    baseline_window_da: float = 0.0     # 0 = 베이스라인 제거 안 함
    smooth_points: int = 7              # 0 또는 1 = 스무딩 안 함 (홀수)
    snr: float = 5.0
    min_rel_intensity: float = 0.5      # 기준 피크 대비 % 이하 제거
    min_distance_da: float = 0.3
    max_peaks: int = 500
    deisotope: str = "none"             # "none" | "mono" | "max"
    isotope_tol_da: float = 0.05


def savgol_coefficients(window: int, order: int = 2) -> np.ndarray:
    """Savitzky–Golay 평활 계수 (중심점 추정)."""
    half = window // 2
    x = np.arange(-half, half + 1, dtype=float)
    a = np.vander(x, order + 1, increasing=True)
    return np.linalg.pinv(a)[0]


def estimate_baseline(mz: np.ndarray, y: np.ndarray, window_da: float) -> np.ndarray:
    """블록별 최소값을 보간하고 이동평균으로 다듬은 베이스라인."""
    if window_da <= 0 or y.size < 10:
        return np.zeros_like(y)
    step = float(np.median(np.diff(mz))) or 1.0
    w = max(5, int(window_da / step))
    n_blocks = max(2, y.size // w)
    edges = np.linspace(0, y.size, n_blocks + 1).astype(int)
    centers, mins = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        if b > a:
            j = a + int(np.argmin(y[a:b]))
            centers.append(mz[j])
            mins.append(y[j])
    base = np.interp(mz, centers, mins)
    kernel = np.ones(w) / w
    pad = np.pad(base, (w // 2, w - 1 - w // 2), mode="edge")
    return np.minimum(np.convolve(pad, kernel, mode="valid"), y)


def pick_peaks(spec: Spectrum, params: PeakPickingParams | None = None) -> list[PickedPeak]:
    """스펙트럼에서 피크 목록을 검출한다 (m/z 오름차순)."""
    p = params or PeakPickingParams()
    mz, y = spec.mz, spec.intensity
    sel = np.ones(mz.size, dtype=bool)
    if p.mz_min is not None:
        sel &= mz >= p.mz_min
    if p.mz_max is not None:
        sel &= mz <= p.mz_max
    mz, y = mz[sel], y[sel].astype(float)
    if mz.size < 3:
        return []

    if spec.centroided:
        noise = float(np.median(y[y > 0])) if np.any(y > 0) else 1.0
        cand = np.nonzero(y > 0)[0]
        ys = y
        snr = y / max(noise, 1e-12)
    else:
        y = y - estimate_baseline(mz, y, p.baseline_window_da)
        y = np.clip(y, 0, None)
        if p.smooth_points and p.smooth_points >= 3:
            w = p.smooth_points | 1
            coef = savgol_coefficients(w)
            ys = np.convolve(np.pad(y, w // 2, mode="edge"), coef[::-1], mode="valid")
        else:
            ys = y
        d = np.diff(y)
        noise = 1.4826 * float(np.median(np.abs(d - np.median(d)))) / np.sqrt(2)
        noise = max(noise, 1e-12)
        snr = ys / noise
        cand = np.nonzero((ys[1:-1] > ys[:-2]) & (ys[1:-1] >= ys[2:]))[0] + 1

    if cand.size == 0:
        return []
    base_peak = float(ys[cand].max())
    keep = (snr[cand] >= p.snr) & (ys[cand] >= base_peak * p.min_rel_intensity / 100.0)
    cand = cand[keep]
    if cand.size == 0:
        return []

    # 최소 간격 억제: 강한 피크부터 채택
    order = cand[np.argsort(-ys[cand], kind="stable")]
    cand_sorted = np.sort(cand)
    cand_mz = mz[cand_sorted]
    suppressed = np.zeros(cand_sorted.size, dtype=bool)
    pos_of = {int(c): i for i, c in enumerate(cand_sorted)}
    accepted: list[int] = []
    for c in order:
        i = pos_of[int(c)]
        if suppressed[i]:
            continue
        accepted.append(int(c))
        lo = np.searchsorted(cand_mz, mz[c] - p.min_distance_da, side="left")
        hi = np.searchsorted(cand_mz, mz[c] + p.min_distance_da, side="right")
        suppressed[lo:hi] = True
        if len(accepted) >= p.max_peaks:
            break

    peaks: list[PickedPeak] = []
    for c in sorted(accepted):
        if spec.centroided:
            cmz = float(mz[c])
        else:
            half = ys[c] / 2.0
            a = c
            while a > 0 and ys[a - 1] > half and c - a < 50:
                a -= 1
            b = c
            while b < ys.size - 1 and ys[b + 1] > half and b - c < 50:
                b += 1
            wts = ys[a:b + 1]
            cmz = float(np.sum(mz[a:b + 1] * wts) / np.sum(wts)) if np.sum(wts) > 0 else float(mz[c])
        peaks.append(PickedPeak(mz=cmz, intensity=float(ys[c]), snr=float(snr[c])))

    if p.deisotope in ("mono", "max"):
        peaks = deisotope(peaks, p.isotope_tol_da, keep=p.deisotope)
    return peaks


def deisotope(peaks: list[PickedPeak], tol: float, keep: str = "mono") -> list[PickedPeak]:
    """
    Δm ≈ 1.00335 간격으로 이어진 피크를 동위원소 클러스터로 묶고 1개만 남긴다 (z=1).

    keep="mono": 클러스터의 첫 피크 (모노이소토픽, 솔버 isotope_offset=0과 대응)
    keep="max":  클러스터의 최대 피크 (솔버에서 동위원소 오프셋 허용 필요)
    """
    if not peaks:
        return []
    mz = np.array([pk.mz for pk in peaks])
    inten = np.array([pk.intensity for pk in peaks])
    cluster = list(range(len(peaks)))
    prev: list[int | None] = [None] * len(peaks)
    falling = [False] * len(peaks)   # 클러스터 포락선이 이미 감소 구간에 들어섰는지
    for j in range(len(peaks)):
        target = mz[j] - ISOTOPE_SPACING
        i = int(np.searchsorted(mz, target - tol))
        best, best_d = None, tol
        while i < j and mz[i] <= target + tol:
            d = abs(mz[i] - target)
            if d <= best_d:
                best, best_d = i, d
            i += 1
        if best is None:
            continue
        # 동위원소 포락선은 단봉형: 감소하던 클러스터에서 강도가 다시 오르면
        # 겹쳐 있는 다른 계열의 피크이므로 새 클러스터로 시작한다.
        if falling[best] and inten[j] > inten[best]:
            continue
        cluster[j] = cluster[best]
        prev[j] = best
        falling[j] = falling[best] or inten[j] < inten[best]
    groups: dict[int, list[int]] = {}
    for j, c in enumerate(cluster):
        groups.setdefault(c, []).append(j)
    out: list[PickedPeak] = []
    for members in groups.values():
        pick = members[0] if keep == "mono" else max(members, key=lambda k: peaks[k].intensity)
        pk = peaks[pick]
        out.append(PickedPeak(pk.mz, pk.intensity, pk.snr, isotope_cluster_size=len(members)))
    out.sort(key=lambda pk: pk.mz)
    return out
