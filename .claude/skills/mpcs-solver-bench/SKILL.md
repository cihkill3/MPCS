---
name: mpcs-solver-bench
description: Benchmark and equivalence-check the MPCS composition solver. Use after any change to mpcs/services/solver_service.py (vectorization, multiprocessing, batch/multi-peak solving, constraint handling) to confirm results are unchanged and to measure the speed-up.
---

# Solver benchmark and equivalence check

Run:
```bash
QT_API=pyqt5 .venv2/Scripts/python.exe .claude/skills/mpcs-solver-bench/bench.py
# options: --peaks 50 --tol 0.05 --quick
```

What it does (see `bench.py`):
1. Builds fixed test systems: (a) 3 linear monomers EO/LA/HDI, (b) the same with an equality constraint `HDI = LA - 1` and an inequality, (c) a BLOCK monomer case.
2. Generates peak m/z values from *known* compositions (so every run has true hits) plus random decoy m/z.
3. Runs `SolverService.solve` per peak, and, if present, `solve_batch` / `solve_multi_peak`, and reports candidates/s and wall time.
4. **Equivalence**: for every peak, compares the set of `(composition, adduct, isotope_offset)` within tolerance between the reference (scalar `solve`) and any new implementation. Any mismatch is printed and the script exits non-zero.

When a refactor adds a new entry point (e.g. a vectorized `solve_batch(peaks, params) -> list[RankedResultSet]`), register it in `IMPLEMENTATIONS` at the top of `bench.py` so it is compared against the reference.

Report the timing table in the final message. A vectorized solver should be ≥ 20× faster on case (a). Compare before/after on the same machine.
