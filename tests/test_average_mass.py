"""
평균 질량(Linear 모드) 솔버 회귀 테스트.

버그: MonomerPanel이 트리 텍스트로 Monomer를 재구성하면서 average_mass가 0으로 초기화되고,
프로젝트 저장 시에도 average_mass가 누락되어 평균 질량 모드 솔버가 후보를 찾지 못했다.
"""

from __future__ import annotations

import json
import os

import pytest

from mpcs.core.atomic_mass_db import ELECTRON_MASS
from mpcs.core.mass_calculator import MassCalculator
from mpcs.infrastructure.project_serializer import ProjectSerializer
from mpcs.models.adduct import Adduct
from mpcs.models.end_group import EndGroup
from mpcs.models.monomer import BlockSubItem, Monomer, MonomerType
from mpcs.models.project import Project
from mpcs.services.constraint_engine import ConstraintEngine
from mpcs.services.solver_service import SolverParams, SolverService

CALC = MassCalculator()


def _eo(lo: int = 0, hi: int = 100) -> Monomer:
    return Monomer.from_formula("EO", MonomerType.MONOMER, "C2H4O", CALC, lo, hi)


def _avg_mz(n: int, monomer: Monomer, adduct: Adduct, eg: EndGroup) -> float:
    return adduct.calc_mz_average(eg.average_mass + n * monomer.average_mass)


@pytest.fixture
def solver() -> SolverService:
    return SolverService(CALC, ConstraintEngine())


def test_average_mode_finds_composition(solver):
    eo, na, eg = _eo(), Adduct("[M+Na]+", enabled=True), EndGroup()
    params = SolverParams(
        peak_mz=_avg_mz(45, eo, na, eg), monomers=[eo], constraints=[],
        end_group=eg, adducts=[na], tolerance_da=0.5, mass_type="AVERAGE",
    )
    best = solver.solve(params).best()
    assert best is not None and best.composition.get("EO") == 45


def test_average_mode_rejects_missing_average_mass(solver):
    eo = _eo()
    eo.average_mass = 0.0
    params = SolverParams(
        peak_mz=2000.0, monomers=[eo], constraints=[], end_group=EndGroup(),
        adducts=[Adduct("[M+Na]+", enabled=True)], mass_type="AVERAGE",
    )
    with pytest.raises(ValueError, match="평균 질량"):
        solver.solve(params)


def test_average_mode_ignores_isotope_offset(solver):
    eo, na, eg = _eo(), Adduct("[M+Na]+", enabled=True), EndGroup()
    params = SolverParams(
        peak_mz=_avg_mz(45, eo, na, eg), monomers=[eo], constraints=[],
        end_group=eg, adducts=[na], tolerance_da=0.5, mass_type="AVERAGE",
        isotope_offset_count=3,
    )
    assert {r.isotope_offset for r in solver.solve(params).results} == {0}


def test_adduct_mass_includes_electron():
    na = Adduct("[M+Na]+")
    assert na.adduct_mass == pytest.approx(22.989769282 - ELECTRON_MASS, abs=1e-9)
    deprot = Adduct("[M-H]-")
    assert deprot.adduct_mass == pytest.approx(-1.00782503223 + ELECTRON_MASS, abs=1e-9)


def test_serializer_roundtrip_keeps_average_mass(tmp_path):
    sub = BlockSubItem("bLA", MonomerType.MONOMER, "C3H4O2", CALC.calc_exact_mass("C3H4O2"),
                       CALC.calc_average_mass("C3H4O2"), 2, 4)
    blk = Monomer("BLK", MonomerType.BLOCK, "~block", 0.0, 0.0, 0, 3, [sub])
    blk.refresh_block_mass()
    project = Project(monomers=[_eo(), blk])
    path = tmp_path / "p.mpcs"
    ProjectSerializer().save(project, path)
    loaded = ProjectSerializer().load(path)
    assert loaded.monomers[0].average_mass == pytest.approx(project.monomers[0].average_mass)
    assert loaded.monomers[1].sub_items[0].average_mass == pytest.approx(sub.average_mass)
    assert loaded.monomers[1].average_mass == pytest.approx(blk.average_mass)


def test_legacy_project_without_average_mass_is_recomputed(tmp_path):
    """스키마 1.0 파일(average_mass 없음, exact_mass 반올림)도 분자식에서 재계산된다."""
    path = tmp_path / "old.mpcs"
    ProjectSerializer().save(Project(monomers=[_eo()]), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "1.0"
    for m in data["monomers"]:
        m.pop("average_mass")
        m["exact_mass"] = 44.0
    path.write_text(json.dumps(data), encoding="utf-8")

    eo = ProjectSerializer().load(path).monomers[0]
    assert eo.exact_mass == pytest.approx(CALC.calc_exact_mass("C2H4O"))
    assert eo.average_mass == pytest.approx(CALC.calc_average_mass("C2H4O"))


def test_monomer_panel_extract_keeps_average_mass():
    """GUI → Project 경로(솔버 실행 직전 호출)에서 평균 질량이 유지되어야 한다."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication
    from mpcs.gui.panels.monomer_panel import MonomerPanel

    app = QApplication.instance() or QApplication([])  # noqa: F841
    sub = BlockSubItem("bLA", MonomerType.MONOMER, "C3H4O2", CALC.calc_exact_mass("C3H4O2"),
                       CALC.calc_average_mass("C3H4O2"), 2, 4)
    blk = Monomer("BLK", MonomerType.BLOCK, "~block", 0.0, 0.0, 0, 3, [sub])
    blk.refresh_block_mass()
    project = Project(monomers=[_eo(), blk])

    panel = MonomerPanel(CALC)
    panel.load_project(project)
    out = Project()
    panel.apply_to_project(out)

    eo = out.monomers[0]
    assert eo.exact_mass == pytest.approx(CALC.calc_exact_mass("C2H4O"), abs=1e-9)
    assert eo.average_mass == pytest.approx(CALC.calc_average_mass("C2H4O"), abs=1e-9)
    assert out.monomers[1].sub_items[0].average_mass == pytest.approx(sub.average_mass)
    assert out.monomers[1].average_mass == pytest.approx(blk.average_mass)
