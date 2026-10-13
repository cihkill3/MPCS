"""
GUI 스모크 테스트 (offscreen): 메인 윈도우에서 피크 목록 → 일괄 솔버 → 결과/계열 연동.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples"


@pytest.fixture(scope="module")
def app():
    from qtpy.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _wait_worker(app, window, timeout=30.0):
    t0 = time.time()
    app.processEvents()
    while window._worker is not None and window._worker.isRunning():
        app.processEvents()
        if time.time() - t0 > timeout:
            raise TimeoutError("solver worker did not finish")
        time.sleep(0.02)
    for _ in range(20):
        app.processEvents()


@pytest.mark.skipif(not (DEMO / "demo_reflectron.mzXML").exists(), reason="demo data missing")
def test_main_window_spectrum_flow(app, monkeypatch):
    from qtpy.QtWidgets import QMessageBox
    from mpcs.gui.main_window import MainWindow
    from mpcs.infrastructure.project_serializer import ProjectSerializer

    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: pytest.fail(f"message box: {a[1:3]}")))

    w = MainWindow(project=ProjectSerializer().load(DEMO / "demo_project.mpcs"))
    monkeypatch.setattr(type(w), "closeEvent", lambda self, e: e.accept())

    # 1) 질량 목록 모드 (프로젝트에 저장된 10개 피크)
    assert w._analysis.peak_count() == 10
    w._solver_control._on_run()
    _wait_worker(app, w)
    rows = w._analysis._rows
    assert all(r.result and r.result.results for r in rows)
    assert rows[0].result.results[0].composition.get("LA") == 5

    # 2) 스펙트럼 → 피크 검출 → 시리즈 → 솔버
    assert w._spectrum_panel.open_file(str(DEMO / "demo_reflectron.mzXML"))
    w._spectrum_panel.apply_preset("reflectron")
    w._spectrum_panel.run_peak_picking()
    assert w._analysis.peak_count() > 100
    assert w._analysis._series and w._analysis._series[0].repeat_name == "EO"
    w._solver_control._on_run()
    _wait_worker(app, w)
    fam = w._analysis._families[0]
    assert fam.adduct_label == "[M+Na]+" and dict(fam.fixed) == {"LA": 5} and fam.support >= 40

    # 3) 후보 선택 → 계열 피크 강조
    sel = w._analysis._current_row()
    assert sel is not None
    assert len(w._analysis._highlight_rows) >= 20

    # 4) 프로젝트 저장 시 피크 목록/스펙트럼 경로 포함
    project = w._collect_project_from_ui()
    assert len(project.peak_data.mz_values) == w._analysis.peak_count()
    assert project.spectrum_path.endswith("demo_reflectron.mzXML")
    w.close()
