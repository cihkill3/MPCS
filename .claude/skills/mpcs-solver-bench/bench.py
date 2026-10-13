"""
MPCS solver benchmark + equivalence check.

Reference = SolverService.solve() called per peak (scalar implementation).
Every entry in IMPLEMENTATIONS is timed and its candidate sets are compared
against the reference. Exit code 1 on any mismatch.

Usage:
    QT_API=pyqt5 .venv2/Scripts/python.exe .claude/skills/mpcs-solver-bench/bench.py [--peaks N] [--tol DA] [--quick]
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mpcs.core.mass_calculator import MassCalculator  # noqa: E402
from mpcs.models.adduct import Adduct  # noqa: E402
from mpcs.models.constraint import Constraint  # noqa: E402
from mpcs.models.end_group import EndGroup  # noqa: E402
from mpcs.models.monomer import BlockSubItem, Monomer, MonomerType  # noqa: E402
from mpcs.models.result import MAX_RESULTS, RankedResultSet  # noqa: E402
from mpcs.services.constraint_engine import ConstraintEngine  # noqa: E402
from mpcs.services.solver_service import SolverParams, SolverService  # noqa: E402

BatchFn = Callable[[SolverService, list[float], SolverParams], list[RankedResultSet]]


def _reference(solver: SolverService, peaks: list[float], params: SolverParams) -> list[RankedResultSet]:
    return [solver.solve(dataclasses.replace(params, peak_mz=mz)) for mz in peaks]


def _multi_peak(solver: SolverService, peaks: list[float], params: SolverParams) -> list[RankedResultSet]:
    return solver.solve_multi_peak(peaks, params)


# Register new implementations here (e.g. a vectorized solve_batch).
IMPLEMENTATIONS: dict[str, BatchFn] = {
    "solve_multi_peak": _multi_peak,
}
if hasattr(SolverService, "solve_batch"):
    IMPLEMENTATIONS["solve_batch"] = lambda s, p, prm: s.solve_batch(p, prm, max_results=MAX_RESULTS)
    IMPLEMENTATIONS["solve_batch(1thr)"] = lambda s, p, prm: s.solve_batch(p, prm, max_results=MAX_RESULTS, workers=1)


# ---------------------------------------------------------------------------
# Test systems
# ---------------------------------------------------------------------------

def _mono(calc: MassCalculator, name: str, formula: str, lo: int, hi: int) -> Monomer:
    return Monomer.from_formula(name, MonomerType.MONOMER, formula, calc, lo, hi)


def build_cases(calc: MassCalculator, quick: bool) -> list[tuple[str, SolverParams, list[dict[str, int]]]]:
    scale = 0.5 if quick else 1.0
    eo = _mono(calc, "EO", "C2H4O", 0, int(120 * scale))
    la = _mono(calc, "LA", "C3H4O2", 0, int(60 * scale))
    hdi = _mono(calc, "HDI", "C8H12N2O2", 0, 10)
    adducts = [Adduct("[M+Na]+", enabled=True), Adduct("[M+K]+", enabled=True)]
    base = dict(end_group=EndGroup(), adducts=adducts, peak_mz=1.0)

    truths_a = [{"EO": e, "LA": l, "HDI": h} for e, l, h in [(40, 10, 2), (55, 20, 3), (30, 25, 1)]]
    case_a = SolverParams(monomers=[eo, la, hdi], constraints=[], **base)

    case_b = SolverParams(
        monomers=[eo, la, hdi],
        constraints=[Constraint("HDI = LA - 1"), Constraint("EO >= LA")],
        **base,
    )
    truths_b = [{"EO": 40, "LA": 4, "HDI": 3}, {"EO": 22, "LA": 8, "HDI": 7}]

    la_sub = BlockSubItem("bLA", MonomerType.MONOMER, "C3H4O2", calc.calc_exact_mass("C3H4O2"),
                          calc.calc_average_mass("C3H4O2"), 2, 6)
    eg_sub = BlockSubItem("bEG", MonomerType.MONOMER, "C2H4O", calc.calc_exact_mass("C2H4O"),
                          calc.calc_average_mass("C2H4O"), 1, 3)
    blk = Monomer("BLK", MonomerType.BLOCK, "block", 0.0, 0.0, 0, 4, [la_sub, eg_sub])
    blk.refresh_block_mass()
    case_c = SolverParams(monomers=[blk, _mono(calc, "EO", "C2H4O", 0, 40)], constraints=[], **base)
    truths_c = [{"BLK": 2, "bLA": 7, "bEG": 3, "EO": 12}]

    from mpcs.models.feed_ratio import FeedRatio, FeedRatioEntry
    from mpcs.models.result import SECData
    case_d = dataclasses.replace(
        case_a,
        feed_ratio=FeedRatio([FeedRatioEntry("EO", 4.0), FeedRatioEntry("LA", 1.0)], tolerance_pct=30.0),
        sec_data=SECData(1500.0, 5000.0, 5000.0 / 1500.0),
    )
    truths_d = [{"EO": 40, "LA": 10, "HDI": 2}]

    return [("a: 3 linear monomers", case_a, truths_a),
            ("d: + feed ratio + SEC", case_d, truths_d),
            ("b: + constraints", case_b, truths_b),
            ("c: block monomer", case_c, truths_c)]


def true_mz(params: SolverParams, counts: dict[str, int], adduct: Adduct) -> float:
    mass = params.end_group.mass
    masses = {m.name: m.exact_mass for m in params.monomers}
    for m in params.monomers:
        for s in m.sub_items:
            masses[s.name] = s.exact_mass
    blocks = {m.name for m in params.monomers if m.monomer_type == MonomerType.BLOCK}
    mass += sum(n * masses[k] for k, n in counts.items() if k not in blocks)
    return adduct.calc_mz(mass)


def key_set(rs: RankedResultSet) -> set[tuple]:
    return {(r.composition.counts, r.adduct_label, r.isotope_offset, r.formula, round(r.error_da, 9))
            for r in rs.results}


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--peaks", type=int, default=20, help="decoy peaks per case")
    ap.add_argument("--tol", type=float, default=0.02)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    random.seed(0)
    calc = MassCalculator()
    solver = SolverService(calc, ConstraintEngine())
    failed = False

    print(f"{'case':28} {'impl':18} {'peaks':>5} {'time s':>8} {'s/peak':>8}  status")
    for name, params, truths in build_cases(calc, args.quick):
        params = dataclasses.replace(params, tolerance_da=args.tol)
        peaks = [true_mz(params, t, params.adducts[0]) for t in truths]
        peaks += [random.uniform(800, 6000) for _ in range(args.peaks)]

        t0 = time.perf_counter()
        ref = _reference(solver, peaks, params)
        t_ref = time.perf_counter() - t0
        print(f"{name:28} {'reference(solve)':18} {len(peaks):5d} {t_ref:8.2f} {t_ref/len(peaks):8.3f}")

        for i, t in enumerate(truths):
            hit = any(r.composition.to_dict().items() >= {k: v for k, v in t.items() if v}.items()
                      for r in ref[i].results)
            if not hit:
                print(f"   !! reference missed true composition {t}")
                failed = True
        if any(rs.count() >= MAX_RESULTS for rs in ref):
            print(f"   (note: some peaks hit MAX_RESULTS={MAX_RESULTS}; comparison is on truncated sets)")

        for impl_name, fn in IMPLEMENTATIONS.items():
            t0 = time.perf_counter()
            try:
                out = fn(solver, peaks, params)
            except Exception as exc:  # report and continue
                print(f"{'':28} {impl_name:18} ERROR {type(exc).__name__}: {exc}")
                failed = True
                continue
            dt = time.perf_counter() - t0
            bad = [i for i, (a, b) in enumerate(zip(ref, out)) if key_set(a) != key_set(b)]
            if len(out) != len(ref):
                bad.append(-1)
            status = "OK" if not bad else f"MISMATCH peaks {bad[:5]}"
            failed |= bool(bad)
            print(f"{'':28} {impl_name:18} {len(peaks):5d} {dt:8.2f} {dt/len(peaks):8.3f}  {status}"
                  f"  (x{t_ref/dt:.1f})")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
