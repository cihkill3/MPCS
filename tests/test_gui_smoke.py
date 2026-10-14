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

    # 4) 결과 요약 띠
    assert w._summary_strip._stack.currentIndex() == 1
    assert "[M+Na]⁺" in w._summary_strip.top.value.text()

    # 5) 프로젝트 저장 시 피크 목록/스펙트럼 경로 포함
    project = w._collect_project_from_ui()
    assert len(project.peak_data.mz_values) == w._analysis.peak_count()
    assert project.spectrum_path.endswith("demo_reflectron.mzXML")
    w.close()


def test_main_window_layout_and_panel_collapse(app, monkeypatch):
    from mpcs.gui.main_window import MainWindow

    w = MainWindow()
    monkeypatch.setattr(type(w), "closeEvent", lambda self, e: e.accept())
    w.resize(1600, 960)
    w.show()
    app.processEvents()
    # 탭 5개 (모노머·제약식은 각각 별도 탭), 메뉴바 대신 명령 막대
    assert w.left_tabs.count() == 5
    assert w._left_titles[:2] == ["모노머", "제약식"]
    assert w._command_bar.isVisible()
    assert {"file", "analysis", "help"} <= set(w._command_bar.menu_buttons)
    assert w._command_bar.action_buttons["run"].action is w.act_run
    # 솔버 설정은 데이터/설정 탭 안에 있다
    assert w._solver_control.isAncestorOf(w._solver_control._tol_spin)
    assert w._spectrum_panel.isAncestorOf(w._solver_control)
    # 입력 패널 접기/펼치기
    w.act_panel.setChecked(False)
    app.processEvents()
    assert not w.left_tabs.isVisible() and w.side_rail.isVisible()
    w.side_rail.tab_requested.emit(2)
    app.processEvents()
    assert w.left_tabs.isVisible() and w.left_tabs.currentIndex() == 2 and w.act_panel.isChecked()
    w.close()


@pytest.mark.skipif(not (DEMO / "demo_reflectron.mzXML").exists(), reason="demo data missing")
def test_language_switch_keeps_state(app, monkeypatch):
    from qtpy.QtWidgets import QMessageBox

    from mpcs.core.i18n import current_language
    from mpcs.gui.main_window import MainWindow
    from mpcs.infrastructure.project_serializer import ProjectSerializer

    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: pytest.fail(f"message box: {a[1:3]}")))
    w = MainWindow(project=ProjectSerializer().load(DEMO / "demo_project.mpcs"))
    monkeypatch.setattr(type(w), "closeEvent", lambda self, e: e.accept())
    assert w._spectrum_panel.open_file(str(DEMO / "demo_reflectron.mzXML"))
    w._spectrum_panel.apply_preset("reflectron")
    w._spectrum_panel.run_peak_picking()
    w._solver_control._on_run()
    _wait_worker(app, w)
    n_peaks = w._analysis.peak_count()
    top = w._analysis._families[0].label()
    w.left_tabs.setCurrentIndex(3)

    en = w.request_language_change("en")
    app.processEvents()
    try:
        assert en is not None and current_language() == "en"
        assert en._left_titles[0] == "Monomers" and en.left_tabs.currentIndex() == 3
        assert en.act_run.text() == "Run solver"
        assert en._analysis.peak_count() == n_peaks
        assert en._analysis._families[0].label() == top
        assert en._spectrum_panel.current_spectrum() is not None
        assert en._solver_control.current_settings()[1] == "EXACT"
        assert en._summary_strip._stack.currentIndex() == 1
        ko = en.request_language_change("ko")
        app.processEvents()
        assert ko._left_titles[0] == "모노머" and ko._analysis.peak_count() == n_peaks
        ko.close()
    finally:
        from mpcs.core.i18n import I18nManager
        I18nManager.get_instance().set_language("ko")


def test_input_panel_can_be_widened(app, monkeypatch):
    from mpcs.gui.main_window import DEFAULT_PANEL_WIDTH, RESULT_MIN_WIDTH, MainWindow

    w = MainWindow()
    monkeypatch.setattr(type(w), "closeEvent", lambda self, e: e.accept())
    w.resize(1600, 960)
    w.show()
    app.processEvents()
    sp = w._main_splitter
    assert sp.handleWidth() >= 5                      # 잡을 수 있는 경계선
    assert sp.sizes()[1] >= DEFAULT_PANEL_WIDTH - 10
    # 넓게 → 창의 절반 이상, 결과 영역은 최소 폭 유지
    w.act_panel_wide.trigger()
    app.processEvents()
    left, right = sp.sizes()[1], sp.sizes()[2]
    assert left >= 0.5 * sum(sp.sizes()) - 10 and right >= RESULT_MIN_WIDTH - 10
    # 다시 누르면 기본 폭
    w.act_panel_wide.trigger()
    app.processEvents()
    assert abs(sp.sizes()[1] - DEFAULT_PANEL_WIDTH) <= 10
    # 직접 지정한 폭은 접었다 펴도 유지
    applied = w.set_panel_width(1000)
    assert applied > DEFAULT_PANEL_WIDTH + 100         # 기본보다 충분히 넓어짐 (창 폭에 따라 상한)
    w.set_panel_collapsed(True)
    w.set_panel_collapsed(False)
    app.processEvents()
    assert abs(sp.sizes()[1] - applied) <= 10
    w.close()


def test_app_icon_present(app):
    from mpcs.gui.dialogs.startup_dialog import StartupDialog
    from mpcs.gui.icons import APP_ICON_DIR, app_icon
    from mpcs.infrastructure.config_manager import RecentProjectsManager

    root = Path(__file__).resolve().parents[1]
    assert (root / "packaging" / "mpcs.ico").stat().st_size > 1000
    assert len(list(APP_ICON_DIR.glob("mpcs_*.png"))) >= 5
    ic = app_icon()
    assert not ic.isNull() and 256 in [s.width() for s in ic.availableSizes()]
    dlg = StartupDialog(RecentProjectsManager())
    assert not dlg.windowIcon().isNull()
    dlg.close()
