"""
스펙트럼 파이프라인 테스트: mzXML 입출력 → 피크 검출 → 시리즈 검출 → 배치 솔버 → 조성 계열 점수.

정답 조성을 알고 있는 합성 스펙트럼(Reflectron / Linear)으로 검증한다.
"""

from __future__ import annotations

import base64
import dataclasses
import zlib

import numpy as np
import pytest

from mpcs.core.mass_calculator import MassCalculator
from mpcs.infrastructure.spectrum_io import read_mzxml, read_spectrum_file, write_mzxml
from mpcs.models.adduct import Adduct
from mpcs.models.constraint import Constraint
from mpcs.models.end_group import EndGroup
from mpcs.models.monomer import BlockSubItem, Monomer, MonomerType
from mpcs.models.spectrum import PickedPeak, Spectrum
from mpcs.services.constraint_engine import ConstraintEngine
from mpcs.services.series_analysis import detect_series, find_spacings, kendrick_mass_defect, score_families
from mpcs.services.solver_service import SolverParams, SolverService
from mpcs.services.spectrum_processing import PeakPickingParams, deisotope, pick_peaks
from mpcs.services.synthetic_spectrum import SeriesSpec, make_polymer_spectrum

CALC = MassCalculator()
NA_SERIES = SeriesSpec("C2H4O", "C15H22O11Na", 15, 70, 40, 8, 1.0)   # EOn LA5 H/OH + Na
K_SERIES = SeriesSpec("C2H4O", "C9H14O7K", 15, 70, 35, 7, 0.5)       # EOn LA3 H/OH + K


@pytest.fixture(scope="module")
def solver() -> SolverService:
    return SolverService(CALC, ConstraintEngine())


def _params(mass_type: str, tol: float) -> SolverParams:
    eo = Monomer.from_formula("EO", MonomerType.MONOMER, "C2H4O", CALC, 0, 80)
    la = Monomer.from_formula("LA", MonomerType.MONOMER, "C3H4O2", CALC, 0, 20)
    adducts = [Adduct("[M+Na]+", enabled=True), Adduct("[M+K]+", enabled=True), Adduct("[M+H]+", enabled=True)]
    return SolverParams(peak_mz=1.0, monomers=[eo, la], constraints=[], end_group=EndGroup("H/OH"),
                        adducts=adducts, tolerance_da=tol, mass_type=mass_type)


# ---------------------------------------------------------------------------
# mzXML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("compress", [True, False])
def test_mzxml_roundtrip(tmp_path, compress):
    s = Spectrum(np.array([100.0, 200.5, 300.25]), np.array([1.0, 5.0, 2.0]), rt_sec=12.5)
    path = tmp_path / "a.mzXML"
    write_mzxml([s, dataclasses.replace(s, scan_num=2, rt_sec=30.0)], path, compress=compress)
    f = read_mzxml(path)
    assert len(f.scans) == 2
    np.testing.assert_allclose(f.scans[0].mz, s.mz, rtol=1e-6)
    np.testing.assert_allclose(f.scans[0].intensity, s.intensity, rtol=1e-6)
    assert f.scans[1].rt_sec == pytest.approx(30.0)


def test_mzxml_64bit_int_mz_order_and_nested_scan(tmp_path):
    pairs = np.array([[10.0, 500.0], [20.0, 600.0]], dtype=">f8")   # int-m/z 순서
    b64 = base64.b64encode(zlib.compress(pairs.tobytes())).decode()
    xml = f"""<?xml version="1.0"?>
<mzXML xmlns="http://sashimi.sourceforge.net/schema_revision/mzXML_2.1"><msRun>
 <scan num="1" msLevel="1" peaksCount="2" retentionTime="PT1M2.5S">
  <peaks precision="64" byteOrder="network" pairOrder="int-m/z" compressionType="zlib">{b64}</peaks>
  <scan num="2" msLevel="2" peaksCount="0"><peaks precision="32" byteOrder="network" pairOrder="m/z-int"></peaks></scan>
 </scan></msRun></mzXML>"""
    path = tmp_path / "b.mzXML"
    path.write_text(xml)
    f = read_mzxml(path)
    ms1 = f.ms1_scans()
    assert [s.scan_num for s in f.scans] == [1, 2]
    np.testing.assert_allclose(ms1[0].mz, [500.0, 600.0])
    np.testing.assert_allclose(ms1[0].intensity, [10.0, 20.0])
    assert ms1[0].rt_sec == pytest.approx(62.5)


def test_text_spectrum(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("# comment\nm/z\tintensity\n100.5\t3\n101.5\t4\n")
    s = read_spectrum_file(path).scans[0]
    np.testing.assert_allclose(s.mz, [100.5, 101.5])


# ---------------------------------------------------------------------------
# Batch solver ≡ reference solve
# ---------------------------------------------------------------------------

def test_batch_matches_reference_with_constraints_and_block(solver):
    sub = BlockSubItem("bLA", MonomerType.MONOMER, "C3H4O2", CALC.calc_exact_mass("C3H4O2"),
                       CALC.calc_average_mass("C3H4O2"), 1, 3)
    blk = Monomer("BLK", MonomerType.BLOCK, "~block", 0.0, 0.0, 0, 3, [sub])
    blk.refresh_block_mass()
    eo = Monomer.from_formula("EO", MonomerType.MONOMER, "C2H4O", CALC, 0, 40)
    hdi = Monomer.from_formula("HDI", MonomerType.MONOMER, "C8H12N2O2", CALC, 0, 6)
    params = SolverParams(peak_mz=1.0, monomers=[blk, eo, hdi],
                          constraints=[Constraint("HDI = BLK + 1"), Constraint("EO >= 2*bLA")],
                          end_group=EndGroup(), adducts=[Adduct("[M+Na]+", enabled=True)],
                          tolerance_da=0.05)
    peaks = [1253.6, 987.45, 1600.8, 2050.1]
    batch = solver.solve_batch(peaks, params, max_results=100)
    for mz, got in zip(peaks, batch):
        ref = solver.solve(dataclasses.replace(params, peak_mz=mz))
        key = lambda rs: {(r.composition.counts, r.adduct_label, r.formula) for r in rs.results}  # noqa: E731
        assert key(got) == key(ref)


# ---------------------------------------------------------------------------
# Peak picking / series / families
# ---------------------------------------------------------------------------

def test_deisotope_splits_overlapping_series():
    # 클러스터 A: 100, 101(최대), 102, 103(감소) + 104에서 다시 상승 → 별도 계열
    mz = [1000.0, 1001.00335, 1002.0067, 1003.01, 1004.0134]
    it = [80.0, 100.0, 50.0, 10.0, 90.0]
    out = deisotope([PickedPeak(m, i) for m, i in zip(mz, it)], tol=0.02, keep="mono")
    assert [round(p.mz, 2) for p in out] == [1000.0, 1004.01]


def test_reflectron_pipeline_recovers_true_families(solver):
    spec = make_polymer_spectrum([NA_SERIES, K_SERIES], 1000, 4000, resolution=12000)
    peaks = pick_peaks(spec, PeakPickingParams(snr=5, smooth_points=5, deisotope="mono"))
    mz = np.array([p.mz for p in peaks])

    spacing = find_spacings(mz, [p.intensity for p in peaks])[0][0]
    assert spacing == pytest.approx(44.026, abs=0.01)

    series = detect_series(mz, {"EO": 44.0262, "LA": 72.0211}, tol=0.03)
    assert series[0].repeat_name == "EO" and len(series[0].peak_indices) >= 40

    params = _params("EXACT", 0.02)
    results = solver.solve_batch(list(mz), params)
    families = score_families(results, ["EO", "LA"], 0.02)
    labels = [(f.fixed, f.adduct_label) for f in families[:2]]
    assert ((("LA", 5),), "[M+Na]+") in labels
    assert ((("LA", 3),), "[M+K]+") in labels
    assert families[0].support >= 40 and families[0].mean_probability > 0.95

    kmd = kendrick_mass_defect(mz[series[0].peak_indices], 44.0262)
    assert np.ptp(kmd) < 0.05   # 같은 시리즈 → 같은 KMD


def test_linear_average_mode_keeps_truth_in_top_families(solver):
    spec = make_polymer_spectrum([NA_SERIES], 1000, 4000, resolution=600)
    peaks = pick_peaks(spec, PeakPickingParams(snr=5, smooth_points=15, min_distance_da=10))
    mz = np.array([p.mz for p in peaks])
    results = solver.solve_batch(list(mz), _params("AVERAGE", 1.0))
    families = score_families(results, ["EO", "LA"], 1.0)
    # 평균질량에서는 Na⁺ vs K⁺−O 등 거의 동중체 계열이 공존하므로 상위 3개 안에 정답이 있어야 함
    top = [(f.fixed, f.adduct_label) for f in families[:3]]
    assert ((("LA", 5),), "[M+Na]+") in top
    assert all(r.isotope_offset == 0 for rs in results for r in rs.results)
