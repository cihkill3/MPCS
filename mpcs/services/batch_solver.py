"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Vectorized Batch Solver

여러 피크를 한 번의 조성 전수탐색으로 동시에 푼다.

알고리즘:
    1. 독립 변수 탐색 공간(모노머 범위, Block 상태)을 혼합 기수(mixed radix) 인덱스로 표현
    2. 청크(기본 2^20개) 단위로 NumPy 배열 생성
    3. 등식 제약식으로 종속 변수 결정 (sympy → numpy lambdify), 불등식/범위/공급비/SEC 필터를 배열 마스크로 적용
    4. 중성 질량 배열 계산 후 정렬 → 모든 (피크, 어덕트, 동위원소 오프셋) 목표값에 대해 searchsorted
    5. 청크는 스레드 풀에서 병렬 처리 (NumPy 연산은 GIL을 해제함), 피크별 상위 K개만 병합 유지

SolverService.solve()(스칼라 루프)는 기준 구현(reference)으로 유지되며,
본 모듈의 결과는 .claude/skills/mpcs-solver-bench 로 동등성을 검증한다.
"""

from __future__ import annotations

from mpcs.core.i18n import tr
import itertools
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from sympy import lambdify

from mpcs.core.formula_parser import FormulaParser
from mpcs.models.adduct import Adduct
from mpcs.models.monomer import MonomerType
from mpcs.models.result import Composition, RankedResultSet, SolverResult
from mpcs.services.constraint_engine import ConstraintEngine, ParsedConstraint

_ISOTOPE_SPACING = 1.00335  # 13C - 12C (Da), SolverService.solve()와 동일
_CHUNK_SIZE = 1 << 20
_EPS = 1e-9


# ---------------------------------------------------------------------------
# 준비 단계
# ---------------------------------------------------------------------------

@dataclass
class _Factor:
    """탐색 공간의 한 축 (일반 모노머 1개 또는 Block 1개)."""

    names: list[str]
    values: np.ndarray  # (n_states, len(names)) int64


@dataclass
class _Prepared:
    var_names: list[str]                       # 결과 조성에 포함되는 모든 변수 (열 순서)
    factors: list[_Factor]
    strides: list[int]
    total: int
    constraints: list[ParsedConstraint]
    dependent_vars: set[str]
    dep_ranges: dict[str, tuple[int, int]]
    block_rules: list[tuple[str, list[tuple[str, int, int]]]]
    mass_vec: np.ndarray                       # var_names 순서의 질량 (Block 이름은 0)
    end_group_mass: float
    numpy_fns: dict[int, tuple[Callable, Callable]] = field(default_factory=dict)


def _prepare(params, engine: ConstraintEngine) -> _Prepared:
    use_avg = params.mass_type == "AVERAGE"
    monomer_names: list[str] = []
    block_names: set[str] = set()
    mass_map: dict[str, float] = {}

    for m in params.monomers:
        monomer_names.append(m.name)
        mass_map[m.name] = m.effective_average_mass() if use_avg else m.effective_mass()
        if m.monomer_type == MonomerType.BLOCK and m.sub_items:
            block_names.add(m.name)
            for sub in m.sub_items:
                monomer_names.append(sub.name)
                mass_map[sub.name] = sub.average_mass if use_avg else sub.exact_mass

    end_group_mass = params.end_group.average_mass if use_avg else params.end_group.mass
    mass_map["EndGroup"] = end_group_mass
    for adduct in params.adducts:
        if adduct.label not in mass_map:
            mass_map[adduct.label] = adduct.adduct_average_mass if use_avg else adduct.adduct_mass

    parsed = engine.parse_all(params.constraints, monomer_names, mass_map)
    constraints = engine.topological_sort(parsed)
    dependent_vars = {pc.equality_lhs for pc in constraints if pc.equality_lhs is not None}

    factors: list[_Factor] = []
    for m in params.monomers:
        if m.name in dependent_vars:
            continue
        if m.monomer_type == MonomerType.BLOCK and m.sub_items:
            names = [m.name] + [s.name for s in m.sub_items]
            rows: list[tuple[int, ...]] = []
            for b in m.search_range():
                if b == 0:
                    rows.append((0,) * len(names))
                    continue
                sub_ranges = [
                    [0] if s.name in dependent_vars else range(b * s.count_min, b * s.count_max + 1)
                    for s in m.sub_items
                ]
                rows.extend((b, *combo) for combo in itertools.product(*sub_ranges))
            values = np.array(rows, dtype=np.int64).reshape(len(rows), len(names))
        else:
            names = [m.name]
            values = np.arange(m.min_count, m.max_count + 1, dtype=np.int64).reshape(-1, 1)
        factors.append(_Factor(names, values))

    var_names: list[str] = []
    for f in factors:
        for n in f.names:
            if n not in var_names:
                var_names.append(n)
    for n in sorted(dependent_vars):
        if n not in var_names:
            var_names.append(n)

    # 혼합 기수: 마지막 축이 가장 빠르게 변함 (itertools.product 순서)
    sizes = [len(f.values) for f in factors]
    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    total = int(np.prod(sizes, dtype=object)) if sizes else 1

    dep_ranges = {
        m.name: (m.min_count, m.max_count) for m in params.monomers if m.name in dependent_vars
    }
    block_rules = [
        (m.name, [(s.name, s.count_min, s.count_max) for s in m.sub_items])
        for m in params.monomers
        if m.monomer_type == MonomerType.BLOCK and m.sub_items
    ]
    mass_vec = np.array(
        [0.0 if (n in block_names or n not in mass_map) else mass_map[n] for n in var_names]
    )

    prep = _Prepared(
        var_names=var_names, factors=factors, strides=strides, total=total,
        constraints=constraints, dependent_vars=dependent_vars, dep_ranges=dep_ranges,
        block_rules=block_rules, mass_vec=mass_vec, end_group_mass=end_group_mass,
    )
    for i, pc in enumerate(constraints):
        prep.numpy_fns[i] = (_numpy_fn(pc, pc.lhs_expr, pc.compiled_lhs),
                             _numpy_fn(pc, pc.rhs_expr, pc.compiled_rhs))
    return prep


def _numpy_fn(pc: ParsedConstraint, expr, scalar_fn) -> Callable:
    """sympy 식을 numpy 배열 함수로 변환. 실패 시 스칼라 함수를 원소별로 적용."""
    import sympy

    by_name = {str(s): s for s in expr.free_symbols}
    symbols = [by_name.get(n, sympy.Symbol(n)) for n in pc.args_tuple]
    try:
        return lambdify(symbols, expr, "numpy")
    except Exception:
        return np.vectorize(scalar_fn, otypes=[float]) if pc.args_tuple else (lambda: scalar_fn())


def _eval_array(fn: Callable, args: list[np.ndarray], size: int) -> np.ndarray:
    with np.errstate(all="ignore"):
        out = fn(*args)
    out = np.asarray(out, dtype=float)
    if out.shape != (size,):
        out = np.broadcast_to(out, (size,)).astype(float)
    return out


# ---------------------------------------------------------------------------
# 분자식 생성 (SolverService._build_ion_formula와 동일한 규칙, 사전 파싱으로 고속화)
# ---------------------------------------------------------------------------

class _FormulaBuilder:
    def __init__(self, monomers, end_group, adducts: list[Adduct]) -> None:
        parser = FormulaParser()
        self._name_elems: dict[str, dict[str, int] | None] = {}
        self._block_names: set[str] = set()

        def _parse(f: str) -> dict[str, int] | None:
            if f.startswith("~"):
                return None
            try:
                float(f)
                return None
            except ValueError:
                pass
            try:
                return parser.parse(f)
            except Exception:
                return None

        for m in monomers:
            if m.monomer_type == MonomerType.BLOCK:
                self._block_names.add(m.name)
                for sub in m.sub_items:
                    self._name_elems[sub.name] = _parse(sub.formula_or_mass)
            else:
                self._name_elems[m.name] = None if m.formula.startswith("~") else _try(parser, m.formula)

        self._eg: dict[str, int] | None = {}
        if end_group.is_custom_mass:
            self._eg = None
        else:
            for part in end_group.formula.split("/"):
                part = part.strip()
                if not part or part.lower() == "cyclized":
                    continue
                e = _try(parser, part)
                if e is None:
                    self._eg = None
                    break
                for el, c in e.items():
                    self._eg[el] = self._eg.get(el, 0) + c

        self._adduct: dict[str, dict[str, int] | None] = {}
        for a in adducts:
            self._adduct[a.label] = _adduct_elements(parser, a.label)

    def build(self, values: dict[str, int], adduct_label: str) -> str | None:
        total: dict[str, int] = {}
        for name, count in values.items():
            if count <= 0 or name in self._block_names:
                continue
            if name not in self._name_elems:
                return None
            elems = self._name_elems[name]
            if elems is None:
                return None
            for el, c in elems.items():
                total[el] = total.get(el, 0) + c * count
        if self._eg is None:
            return None
        for el, c in self._eg.items():
            total[el] = total.get(el, 0) + c
        add = self._adduct.get(adduct_label)
        if add is None:
            return None
        for el, c in add.items():
            total[el] = total.get(el, 0) + c
        from mpcs.services.solver_service import _elements_to_formula
        return _elements_to_formula(total)


def _try(parser: FormulaParser, f: str) -> dict[str, int] | None:
    try:
        return parser.parse(f)
    except Exception:
        return None


def _adduct_elements(parser: FormulaParser, label: str) -> dict[str, int] | None:
    elems: dict[str, int] = {}
    m = re.match(r'^\[M([+-].*?)\](\d*)([+-])?$', label.strip())
    if not m:
        return elems
    for sign, part in re.findall(r'([+-])([^+-]+)', m.group(1)):
        part = part.strip()
        m_num = re.match(r'^(\d+)(.+)$', part)
        if m_num:
            part = f"({m_num.group(2)}){m_num.group(1)}"
        e = _try(parser, part)
        if e is None:
            return None
        for el, c in e.items():
            elems[el] = elems.get(el, 0) + (c if sign == "+" else -c)
    return elems


# ---------------------------------------------------------------------------
# 청크 처리
# ---------------------------------------------------------------------------

@dataclass
class _Targets:
    """모든 (피크, 어덕트, 오프셋) 조합의 중성 질량 목표값."""

    peak_idx: np.ndarray
    adduct_idx: np.ndarray
    offset: np.ndarray
    center: np.ndarray       # 목표 중성 질량
    half_width: np.ndarray   # tol × z


def _build_targets(peaks: np.ndarray, params) -> tuple[_Targets, list[float], list[int]]:
    use_avg = params.mass_type == "AVERAGE"
    n_off = params.isotope_offset_count if not use_avg else 0
    add_mass = [a.adduct_average_mass if use_avg else a.adduct_mass for a in params.adducts]
    charges = [a.charge for a in params.adducts]
    p_idx, a_idx, offs, cen, hw = [], [], [], [], []
    for ai, (am, z) in enumerate(zip(add_mass, charges)):
        for n in range(n_off + 1):
            p_idx.append(np.arange(len(peaks)))
            a_idx.append(np.full(len(peaks), ai))
            offs.append(np.full(len(peaks), n))
            cen.append(peaks * z - am - _ISOTOPE_SPACING * n)
            hw.append(np.full(len(peaks), params.tolerance_da * z))
    cat = np.concatenate
    return _Targets(cat(p_idx), cat(a_idx), cat(offs), cat(cen), cat(hw)), add_mass, charges


def _process_chunk(prep: _Prepared, params, start: int, stop: int, targets: _Targets,
                   peaks: np.ndarray, add_mass: list[float], charges: list[int]):
    """[start, stop) 인덱스 구간을 평가해 피크별 매칭 후보를 반환한다."""
    size = stop - start
    idx = np.arange(start, stop, dtype=np.int64)
    zeros = np.zeros(size, dtype=np.int64)
    vals: dict[str, np.ndarray] = {}

    for f, stride in zip(prep.factors, prep.strides):
        state = (idx // stride) % len(f.values)
        cols = f.values[state]
        for j, name in enumerate(f.names):
            vals[name] = vals[name] + cols[:, j] if name in vals else cols[:, j]
    for name in prep.var_names:
        vals.setdefault(name, zeros)

    valid = np.ones(size, dtype=bool)

    for i, pc in enumerate(prep.constraints):
        lhs_fn, rhs_fn = prep.numpy_fns[i]
        args = [vals.get(n, zeros) for n in pc.args_tuple]
        if pc.equality_lhs is not None and pc.equality_lhs in prep.dependent_vars:
            r = _eval_array(rhs_fn, args, size)
            rounded = np.rint(r)
            ok = np.isfinite(r) & (np.abs(r - rounded) <= _EPS) & (rounded >= 0)
            valid &= ok
            vals[pc.equality_lhs] = np.where(ok, rounded, 0).astype(np.int64)
        else:
            lv = _eval_array(lhs_fn, args, size)
            rv = _eval_array(rhs_fn, args, size)
            op = pc.comparison
            if op == "=":
                ok = np.abs(lv - rv) < _EPS
            elif op == "<":
                ok = lv < rv
            elif op == "<=":
                ok = lv <= rv
            elif op == ">":
                ok = lv > rv
            else:
                ok = lv >= rv
            valid &= ok & np.isfinite(lv) & np.isfinite(rv)

    for name, (lo, hi) in prep.dep_ranges.items():
        v = vals[name]
        valid &= (v >= lo) & (v <= hi)

    for block, subs in prep.block_rules:
        b = vals.get(block, zeros)
        for sub_name, cmin, cmax in subs:
            s = vals.get(sub_name, zeros)
            valid &= (s >= b * cmin) & (s <= b * cmax)

    if params.feed_ratio is not None:
        valid &= params.feed_ratio.check_composition_array(vals, size)

    comp = np.stack([vals[n] for n in prep.var_names], axis=1) if prep.var_names else np.zeros((size, 0), np.int64)
    mass = prep.end_group_mass + (np.where(comp > 0, comp, 0) * prep.mass_vec).sum(axis=1)

    if params.sec_data is not None:
        valid &= (mass >= params.sec_data.mn) & (mass <= params.sec_data.mw)

    rows = np.nonzero(valid)[0]
    if rows.size == 0:
        return {}, 0
    m_valid = mass[rows]
    order = np.argsort(m_valid, kind="stable")
    m_sorted = m_valid[order]

    lo = np.searchsorted(m_sorted, targets.center - targets.half_width - 1e-6, side="left")
    hi = np.searchsorted(m_sorted, targets.center + targets.half_width + 1e-6, side="right")

    out: dict[int, list] = {}
    for t in np.nonzero(hi > lo)[0]:
        sel = rows[order[lo[t]:hi[t]]]
        ai = int(targets.adduct_idx[t])
        n = int(targets.offset[t])
        z = charges[ai]
        theo = (mass[sel] + add_mass[ai]) / z
        p = int(targets.peak_idx[t])
        err = np.abs(peaks[p] - (theo + _ISOTOPE_SPACING * n / z))
        keep = err <= params.tolerance_da
        if not keep.any():
            continue
        out.setdefault(p, []).append((err[keep], theo[keep], np.full(int(keep.sum()), ai),
                                      np.full(int(keep.sum()), n), comp[sel[keep]]))
    return out, int(rows.size)


def _merge(acc: dict[int, tuple], new: dict[int, list], k: int) -> None:
    """피크별 후보를 병합하고 오차 기준 상위 k개만 유지한다."""
    for p, parts in new.items():
        if p in acc:
            parts = [acc[p]] + parts
        err = np.concatenate([x[0] for x in parts])
        theo = np.concatenate([x[1] for x in parts])
        ai = np.concatenate([x[2] for x in parts])
        n = np.concatenate([x[3] for x in parts])
        comp = np.concatenate([x[4] for x in parts], axis=0)
        if err.size > k:
            keep = np.argpartition(err, k - 1)[:k]
            err, theo, ai, n, comp = err[keep], theo[keep], ai[keep], n[keep], comp[keep]
        acc[p] = (err, theo, ai, n, comp)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def solve_batch(
    engine: ConstraintEngine,
    peak_mz_list: list[float],
    params,
    max_results: int = 2000,
    progress_callback: Callable[[int, int, int], None] | None = None,
    cancel_flag: Callable[[], bool] | None = None,
    workers: int | None = None,
) -> list[RankedResultSet]:
    """
    여러 m/z 피크를 한 번의 전수탐색으로 푼다.

    Args:
        engine:        제약식 엔진
        peak_mz_list:  관측 m/z 목록
        params:        SolverParams (peak_mz는 무시)
        max_results:   피크당 보관할 최대 후보 수 (오차 오름차순). 계열 점수에는 넉넉히 필요
        progress_callback: (처리한 조합 수, 유효 조합 수, 전체 조합 수)
        cancel_flag:   True 반환 시 남은 청크를 건너뜀
        workers:       스레드 수 (None → CPU 수, 최대 8)

    Returns:
        입력 순서와 같은 RankedResultSet 리스트
    """
    import dataclasses

    if not peak_mz_list:
        return []
    errors = dataclasses.replace(params, peak_mz=max(peak_mz_list[0], 1e-9)).validate()
    if errors:
        raise ValueError(tr('솔버 파라미터 오류: {v}', v='; '.join(errors)))

    prep = _prepare(params, engine)
    peaks = np.asarray(peak_mz_list, dtype=float)
    targets, add_mass, charges = _build_targets(peaks, params)

    chunks = [(s, min(s + _CHUNK_SIZE, prep.total)) for s in range(0, prep.total, _CHUNK_SIZE)]
    n_workers = workers or min(8, os.cpu_count() or 1)
    acc: dict[int, tuple] = {}
    processed = 0
    valid_total = 0

    def _run(chunk):
        if cancel_flag is not None and cancel_flag():
            return None
        return _process_chunk(prep, params, chunk[0], chunk[1], targets, peaks, add_mass, charges)

    if len(chunks) <= 1 or n_workers <= 1:
        results_iter = map(_run, chunks)
        pool = None
    else:
        pool = ThreadPoolExecutor(max_workers=n_workers)
        results_iter = pool.map(_run, chunks)
    try:
        for chunk, res in zip(chunks, results_iter):
            if res is None:
                continue
            found, n_valid = res
            _merge(acc, found, max_results)
            processed += chunk[1] - chunk[0]
            valid_total += n_valid
            if progress_callback is not None:
                progress_callback(processed, valid_total, prep.total)
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)

    builder = _FormulaBuilder(params.monomers, params.end_group, params.adducts)
    out: list[RankedResultSet] = []
    for p, mz in enumerate(peak_mz_list):
        results: list[SolverResult] = []
        if p in acc:
            err, theo, ai, n, comp = acc[p]
            order = np.lexsort((ai, n, err))
            for r in order:
                values = {name: int(comp[r, j]) for j, name in enumerate(prep.var_names)}
                adduct = params.adducts[int(ai[r])]
                results.append(SolverResult(
                    composition=Composition(values),
                    calculated_mass=float(theo[r]),
                    observed_mass=float(mz),
                    error_da=float(err[r]),
                    adduct_label=adduct.label,
                    isotope_offset=int(n[r]),
                    formula=builder.build(values, adduct.label),
                ))
        out.append(RankedResultSet(peak_mz=float(mz), results=results))
    return out
