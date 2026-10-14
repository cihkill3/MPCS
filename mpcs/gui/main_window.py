"""
MPCS — MALDI Polymer Composition Solver
GUI: Main Window

SRS §4 GUI Layout / §4.2 Project Section (New/Open/Save/SaveAs)

구성 (v1.3, PepLCMS UI 키트를 복사해 MPCS용으로 독립 관리):
    맨 위       CommandBar 한 줄 — [파일 분석 도움말] 메뉴 버튼 │ 입력 패널·열기·저장·스펙트럼 │
                ▶ 솔버 실행(F5)·중단 │ 내보내기 ▾ … 언어 ▾   (QMenuBar 없음)
    좌측        입력 패널 탭: 모노머 / 제약식 / 말단기·어덕트 / 데이터·설정(솔버 설정 + 스펙트럼) / 중합 계산기
                접으면 SideRail(40 px 아이콘 막대) — Ctrl+B, 명령 막대 버튼, 스플리터 손잡이 두 번 누름
    우측        ResultSummaryStrip (최상위 조성 계열) → AnalysisView
                (스펙트럼 ↔ 피크 목록 ↔ 후보 조성 / 조성 계열 / KMD / 메시지)
단축키: F5 솔버 실행, Esc 중단, Ctrl+B 입력 패널, Ctrl+O/S 열기/저장, Ctrl+Shift+O 스펙트럼 열기, F1 이용 안내.
언어 즉시 전환(명령 막대 KO/EN): 입력·스펙트럼·피크·결과 상태를 그대로 옮긴 새 창을 만들고 이 창은 닫는다.
창 크기·입력 패널 접힘·스플리터는 app_config.json에 저장한다.
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from qtpy.QtCore import QByteArray, QEvent, Qt, QTimer, Signal
from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.formatting import ion_text
from mpcs.core.i18n import I18nManager, current_language, tr
from mpcs.core.mass_calculator import MassCalculator
from mpcs.gui import theme
from mpcs.gui.command_bar import CommandBar
from mpcs.gui.dialogs.guide_dialog import GuideDialog
from mpcs.gui.icons import app_icon, app_pixmap, icon
from mpcs.gui.panels.adduct_panel import AdductPanel
from mpcs.gui.panels.constraint_panel import ConstraintPanel
from mpcs.gui.panels.end_group_panel import EndGroupPanel
from mpcs.gui.panels.monomer_panel import MonomerPanel
from mpcs.gui.panels.polymerization_panel import PolymerizationPanel
from mpcs.gui.panels.solver_control_panel import SolverControlPanel
from mpcs.gui.panels.spectrum_panel import SpectrumPanel, peaks_to_rows
from mpcs.gui.side_rail import RAIL_WIDTH, PanelSplitter, SideRail
from mpcs.gui.views.analysis_view import AnalysisView
from mpcs.gui.views.summary_strip import ResultSummaryStrip
from mpcs.gui.widgets import caption
from mpcs.gui.workers.solver_worker import BatchSolverWorker
from mpcs.infrastructure.config_manager import AppConfigManager, RecentProjectsManager
from mpcs.infrastructure.project_serializer import (
    PROJECT_FILE_EXTENSION,
    ProjectDeserializeError,
    ProjectSerializeError,
    ProjectSerializer,
)
from mpcs.models.monomer import MonomerType
from mpcs.models.project import Project
from mpcs.services.constraint_engine import CircularDependencyError, ConstraintEngine
from mpcs.services.solver_service import SolverParams, SolverService

APP_TITLE = "MALDI Polymer Composition Solver"
DEFAULT_PANEL_WIDTH = 720      # 입력 패널 기본 폭 (px)
RESULT_MIN_WIDTH = 560         # 입력 패널을 넓혀도 결과 영역은 이 폭 이상 남긴다

# ----------------------------------------------------------------------
# Qt 표준 대화상자 번역 · 창 교체 (PepLCMS main_window에서 복사)
# ----------------------------------------------------------------------
_QT_TRANSLATOR: dict = {"obj": None}


def install_qt_translator(lang: str) -> bool:
    """
    Qt 표준 대화상자 문구(저장/취소/닫기 등) 번역을 언어에 맞춘다.
    ko → qtbase_ko 설치, en → 설치된 번역 제거. 설치했으면 True.
    """
    from qtpy.QtCore import QLibraryInfo, QTranslator

    app = QApplication.instance()
    if app is None:
        return False
    old = _QT_TRANSLATOR["obj"]
    if old is not None:
        try:
            app.removeTranslator(old)
        except RuntimeError:
            pass
        _QT_TRANSLATOR["obj"] = None
    if lang != "ko":
        return False
    tr_qt = QTranslator()
    if tr_qt.load("qtbase_ko", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr_qt)
        _QT_TRANSLATOR["obj"] = tr_qt
        return True
    return False


def _dispose_window(win) -> None:
    """언어 전환으로 대체된 창을 파괴하고 파이썬 쪽 참조를 버린다 (sip 래퍼 재사용 문제 방지)."""
    import gc

    try:
        from qtpy import sip
        if not sip.isdeleted(win):
            sip.delete(win)
    except Exception:  # noqa: BLE001
        try:
            win.deleteLater()
        except RuntimeError:
            pass
    try:
        win.__dict__.clear()
    except Exception:  # noqa: BLE001
        pass
    gc.collect()


class MainWindow(QMainWindow):
    """MPCS 메인 윈도우."""

    window_replaced = Signal(object)

    def __init__(
        self,
        project: Project | None = None,
        recent_manager: RecentProjectsManager | None = None,
        restore_state: dict | None = None,
    ) -> None:
        super().__init__()
        self._calc = MassCalculator()
        self._engine = ConstraintEngine()
        self._solver = SolverService(self._calc, self._engine)
        self._serializer = ProjectSerializer()
        self._recent_manager = recent_manager or RecentProjectsManager()
        self._app_config = AppConfigManager()
        self._current_filepath: str | None = None
        self._worker: BatchSolverWorker | None = None
        self._solve_rows: list[int] = []
        self._panel_collapsed = False
        self._panel_width = DEFAULT_PANEL_WIDTH
        self.confirm_close = True
        self._project = project or Project()

        self._create_actions()
        self._setup_ui()
        self._setup_status_bar()
        self._connect_signals()
        self._load_project_to_ui(open_spectrum=restore_state is None)
        if restore_state is not None:
            self._apply_state(restore_state)
        else:
            self._restore_window_state()
        self._update_title()
        self.log(tr("준비"))

    # ------------------------------------------------------------------
    # 동작(QAction) · 메뉴
    # ------------------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, tip: str = "", checkable: bool = False) -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        self.addAction(a)          # 메뉴가 닫혀 있어도 단축키 동작
        return a

    def _create_actions(self) -> None:
        A = self._action
        self.act_new = A(tr("새 프로젝트"), self._on_new_project, QKeySequence.New, tr("현재 입력을 지우고 새 프로젝트를 시작합니다."))
        self.act_open = A(tr("프로젝트 열기..."), self._on_open_project, QKeySequence.Open, tr("저장한 프로젝트(.mpcs)를 엽니다."))
        self.act_save = A(tr("저장"), self._on_save_project, QKeySequence.Save, tr("프로젝트를 저장합니다 (모노머·제약식·어덕트·피크 목록·스펙트럼 경로)."))
        self.act_save_as = A(tr("다른 이름으로 저장..."), self._on_save_as_project, "Ctrl+Shift+S", tr("프로젝트를 새 파일로 저장합니다."))
        self.act_exit = A(tr("종료"), self.close, None, tr("프로그램을 종료합니다."))
        self.act_open_spectrum = A(tr("스펙트럼 열기..."), self._on_open_spectrum, "Ctrl+Shift+O",
                                   tr("mzXML 스펙트럼을 열고 데이터/설정 탭으로 이동합니다."))
        self.act_close_spectrum = A(tr("스펙트럼 닫기"), self._on_close_spectrum, None, tr("열린 스펙트럼을 닫습니다 (피크 목록은 유지)."))
        self.act_pick = A(tr("피크 검출"), self._on_pick_peaks, "Ctrl+Shift+P", tr("현재 스펙트럼에서 피크를 검출합니다."))
        self.act_run = A(tr("솔버 실행"), self._on_run_action, "F5",
                         tr("피크 목록의 (체크한) 모든 피크에 대해 조성을 계산하고 조성 계열 확률을 매깁니다."))
        self.act_stop = A(tr("중단"), self._on_cancel_solver, "Esc", tr("실행 중인 솔버를 멈춥니다."))
        self.act_stop.setEnabled(False)
        self.act_panel = A(tr("입력 패널"), self._on_panel_toggled, "Ctrl+B",
                           tr("왼쪽 입력 패널을 접거나 펼칩니다."), checkable=True)
        self.act_panel.blockSignals(True)
        self.act_panel.setChecked(True)
        self.act_panel.blockSignals(False)
        self.act_panel_wide = A(tr("입력 패널 넓게"), self._on_panel_wide, "Ctrl+Shift+B",
                                tr("입력 패널을 창 폭의 절반 정도로 넓힙니다. 다시 누르면 기본 폭으로 돌아갑니다. "
                                   "가운데 경계선을 끌어서 원하는 폭으로 조절할 수도 있습니다."))
        self.act_export_all = A(tr("전체 결과 (엑셀)..."), self._on_export_all, None,
                                tr("피크 요약 · 전체 후보 · 조성 계열을 엑셀 시트로 저장합니다."))
        self.act_export_peak = A(tr("선택한 피크의 후보..."), self._on_export_peak, None,
                                 tr("선택한 피크의 후보 표를 엑셀/CSV로 저장합니다."))
        self.act_guide = A(tr("이용 안내"), self._on_guide, "F1", tr("화면 구성과 사용 순서를 안내합니다."))
        self.act_about = A(tr("MPCS 정보"), self._on_about, None, tr("버전과 제작 정보"))

        self.file_menu = QMenu(tr("파일"), self)
        for a in (self.act_new, self.act_open, None, self.act_save, self.act_save_as, None):
            self.file_menu.addSeparator() if a is None else self.file_menu.addAction(a)
        self.export_menu = QMenu(tr("내보내기"), self)
        self.export_menu.addAction(self.act_export_all)
        self.export_menu.addAction(self.act_export_peak)
        self.file_menu.addMenu(self.export_menu)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.act_exit)

        self.analysis_menu = QMenu(tr("분석"), self)
        for a in (self.act_open_spectrum, self.act_close_spectrum, self.act_pick, None,
                  self.act_run, self.act_stop, None, self.act_panel, self.act_panel_wide):
            self.analysis_menu.addSeparator() if a is None else self.analysis_menu.addAction(a)

        self.help_menu = QMenu(tr("도움말"), self)
        self.help_menu.addAction(self.act_guide)
        self.help_menu.addAction(self.act_about)

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1100, 700)
        self.resize(1600, 960)

        # ── 명령 막대 ─────────────────────────────────────────────────
        bar = CommandBar(self)
        bar.add_menu_button("file", tr("파일"), self.file_menu, "F")
        bar.add_menu_button("analysis", tr("분석"), self.analysis_menu, "A")
        bar.add_menu_button("help", tr("도움말"), self.help_menu, "H")
        bar.addSeparator()
        bar.add_action_button("panel", self.act_panel, tr("입력 패널"), "panel-left")
        bar.add_action_button("open", self.act_open, tr("열기"), "folder-open")
        bar.add_action_button("save", self.act_save, tr("저장"), "save")
        bar.add_action_button("spectrum", self.act_open_spectrum, tr("스펙트럼"), "file-up")
        bar.addSeparator()
        bar.add_action_button("run", self.act_run, tr("솔버 실행"), "play", primary=True)
        bar.add_action_button("stop", self.act_stop, tr("중단"), "square")
        bar.addSeparator()
        bar.add_dropdown("export", tr("내보내기"), "download", self.export_menu, tr("결과를 엑셀/CSV로 저장"))
        bar.add_stretch()
        bar.add_language_button(current_language())
        bar.language_selected.connect(self.request_language_change)
        self.addToolBar(Qt.TopToolBarArea, bar)
        self._command_bar = bar

        # ── 좌측 입력 패널 ─────────────────────────────────────────────
        self._monomer_panel = MonomerPanel(self._calc)
        self._constraint_panel = ConstraintPanel()

        eg_adduct_widget = QWidget()
        eg_layout = QVBoxLayout(eg_adduct_widget)
        eg_layout.setContentsMargins(12, 4, 12, 12)
        eg_layout.setSpacing(4)
        self._end_group_panel = EndGroupPanel()
        self._adduct_panel = AdductPanel()
        eg_layout.addWidget(self._end_group_panel)
        eg_layout.addWidget(self._adduct_panel, 1)
        eg_scroll = QScrollArea()
        eg_scroll.setWidgetResizable(True)
        eg_scroll.setWidget(eg_adduct_widget)

        self._solver_control = SolverControlPanel()
        self._solver_control.run_requested.connect(self._on_run_solver)
        self._solver_control.cancel_requested.connect(self._on_cancel_solver)
        self._spectrum_panel = SpectrumPanel()
        self._spectrum_panel.insert_top(self._solver_control)

        self._poly_panel = PolymerizationPanel()

        self.left_tabs = QTabWidget()
        self.left_tabs.setMinimumWidth(460)
        tabs = [
            (self._monomer_panel, "flask-conical", tr("모노머"), tr("고분자를 이루는 반복 단위(모노머·블록)와 탐색 범위")),
            (self._constraint_panel, "sigma", tr("제약식"), tr("모노머 개수 사이의 규칙 (선택)")),
            (eg_scroll, "link", tr("말단기 / 어덕트"), tr("사슬 말단기와 이온화 어덕트")),
            (self._spectrum_panel, "sliders-horizontal", tr("데이터/설정"),
             tr("솔버 설정(질량 기준·허용 오차), mzXML 스펙트럼, 피크 검출, 주기 시리즈")),
            (self._poly_panel, "calculator", tr("중합 계산기"), tr("레시피와 전환율로 반복 수 범위 예측")),
        ]
        self.side_rail = SideRail()
        for i, (w, ic, title, tip) in enumerate(tabs):
            self.left_tabs.addTab(w, icon(ic, theme.TEXT_2, 16, checked_color=theme.ACCENT), title)
            self.left_tabs.setTabToolTip(i, tip)
            self.side_rail.add_tab_button(ic, f"{title} — {tip}")
        self.side_rail.set_current(0)
        self.side_rail.setVisible(False)
        self._left_titles = [t[2] for t in tabs]
        self.left_tabs.installEventFilter(self)

        # ── 우측 결과 ─────────────────────────────────────────────────
        self._summary_strip = ResultSummaryStrip()
        self._analysis = AnalysisView()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(theme.mono_font(theme.FS_CAPTION))
        self._analysis.add_detail_tab(self.log_view, tr("메시지"), tr("작업 기록 (파일 열기, 피크 검출, 솔버 실행, 오류)"))
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._summary_strip)
        rl.addWidget(self._analysis, 1)
        # 명시적 최소 폭: 스플리터가 내용물의 minimumSizeHint(버튼 줄 등) 대신 이 값을 써서
        # 입력 패널을 넓게 끌 수 있다
        right.setMinimumWidth(RESULT_MIN_WIDTH)

        self._main_splitter = PanelSplitter(Qt.Horizontal)
        self._main_splitter.addWidget(self.side_rail)
        self._main_splitter.addWidget(self.left_tabs)
        self._main_splitter.addWidget(right)
        self._main_splitter.setCollapsible(0, False)
        self._main_splitter.setCollapsible(2, False)
        self._main_splitter.setStretchFactor(1, 0)
        self._main_splitter.setStretchFactor(2, 1)
        self._main_splitter.setSizes([0, self._panel_width, 1040])
        # 경계선: 보이는 선은 1 px, 잡는 영역은 7 px (끌어서 입력 패널 폭 조절)
        t = theme
        self._main_splitter.setObjectName("mainSplitter")
        self._main_splitter.setHandleWidth(7)
        self._main_splitter.setStyleSheet(
            f"QSplitter#mainSplitter::handle:horizontal {{ width: 7px; background: {t.BORDER};"
            f" border-left: 3px solid {t.BG}; border-right: 3px solid {t.BG}; }}"
            f"QSplitter#mainSplitter::handle:horizontal:hover {{ background: {t.ACCENT};"
            f" border-left: 2px solid {t.ACCENT_SOFT}; border-right: 2px solid {t.ACCENT_SOFT}; }}"
        )
        for i in (1, 2):
            self._main_splitter.handle(i).setToolTip(tr("끌어서 입력 패널 폭을 조절합니다 · 두 번 누르면 접거나 펼칩니다"))
        self._main_splitter.splitterMoved.connect(self._on_splitter_moved)
        self.setCentralWidget(self._main_splitter)

    def _setup_status_bar(self) -> None:
        self._status_bar: QStatusBar = self.statusBar()
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedWidth(260)
        self._progress_bar.setToolTip(tr("솔버 진행률"))
        self._progress_label = caption("", wrap=False)
        self._shortcut_hint = caption(tr("F5 솔버 실행 · Ctrl+B 입력 패널 · F1 이용 안내"), wrap=False)
        self._status_bar.addPermanentWidget(self._progress_label)
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.addPermanentWidget(self._shortcut_hint)

    def _connect_signals(self) -> None:
        self._poly_panel.apply_requested.connect(self._monomer_panel.apply_min_max)
        self._poly_panel.sync_requested.connect(self._sync_poly_from_monomers)
        self._monomer_panel.monomers_changed.connect(self._on_monomers_changed)

        self._spectrum_panel.spectrum_loaded.connect(self._on_spectrum_loaded)
        self._spectrum_panel.peaks_picked.connect(self._on_peaks_picked)
        self._spectrum_panel.preset_applied.connect(self._on_preset_applied)
        self._spectrum_panel.series_options_changed.connect(self._update_series)
        self._analysis.peaks_changed.connect(self._update_series)
        for sig in self._solver_control.settings_changed_signal():
            sig.connect(self._update_series)

        self._summary_strip.family_clicked.connect(self._analysis.select_family)
        self.side_rail.expand_requested.connect(lambda: self.set_panel_collapsed(False))
        self.side_rail.tab_requested.connect(self._on_rail_tab)
        self.left_tabs.currentChanged.connect(self.side_rail.set_current)
        self.left_tabs.currentChanged.connect(lambda _i: self._fit_left_tabs())
        self._main_splitter.handle_double_clicked.connect(lambda _i: self.set_panel_collapsed(not self._panel_collapsed))

    # ------------------------------------------------------------------
    # 입력 패널 접기
    # ------------------------------------------------------------------

    def set_panel_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._panel_collapsed:
            return
        sizes = self._main_splitter.sizes()
        if collapsed:
            self._panel_width = max(sizes[1], 400)
            self.left_tabs.setVisible(False)
            self.side_rail.setVisible(True)
            self._main_splitter.setSizes([RAIL_WIDTH, 0, sum(sizes) - RAIL_WIDTH])
        else:
            self.side_rail.setVisible(False)
            self.left_tabs.setVisible(True)
            self._main_splitter.setSizes([0, self._panel_width, max(sum(sizes) - self._panel_width, 400)])
        self._panel_collapsed = collapsed
        self.act_panel.blockSignals(True)
        self.act_panel.setChecked(not collapsed)
        self.act_panel.blockSignals(False)
        btn = self._command_bar.action_buttons.get("panel")
        if btn is not None:
            btn.sync()

    def _on_panel_toggled(self, checked: bool) -> None:
        self.set_panel_collapsed(not checked)

    def _on_rail_tab(self, index: int) -> None:
        self.set_panel_collapsed(False)
        self.left_tabs.setCurrentIndex(index)

    def set_panel_width(self, width: int) -> int:
        """입력 패널 폭을 정한다 (결과 영역은 RESULT_MIN_WIDTH 이상 남김). 실제 적용한 폭을 반환."""
        self.set_panel_collapsed(False)
        sizes = self._main_splitter.sizes()
        total = sum(sizes) - sizes[0]
        width = int(max(self.left_tabs.minimumWidth(), min(width, total - RESULT_MIN_WIDTH)))
        self._main_splitter.setSizes([0, width, total - width])
        self._panel_width = width
        return width

    def _wide_width(self) -> int:
        total = sum(self._main_splitter.sizes())
        return max(int(total * 0.55), DEFAULT_PANEL_WIDTH + 200)

    def _on_panel_wide(self) -> None:
        """넓게 ↔ 기본 폭 전환."""
        sizes = self._main_splitter.sizes()
        is_wide = not self._panel_collapsed and sizes[1] > DEFAULT_PANEL_WIDTH + 50
        applied = self.set_panel_width(DEFAULT_PANEL_WIDTH if is_wide else self._wide_width())
        self.log(tr("입력 패널 폭: {w}px", w=applied))

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """경계선을 끌어 바꾼 폭을 기억한다 (접었다 펼 때, 다음 실행 때 같은 폭)."""
        if not self._panel_collapsed:
            w = self._main_splitter.sizes()[1]
            if w > 0:
                self._panel_width = w

    def eventFilter(self, obj, ev):  # noqa: N802
        if obj is getattr(self, "left_tabs", None) and ev.type() == QEvent.Resize:
            self._fit_left_tabs()
        return super().eventFilter(obj, ev)

    def _fit_left_tabs(self) -> None:
        """탭 이름이 패널 폭에 다 들어가지 않으면 아이콘만 보인다 (이름은 툴팁)."""
        bar = self.left_tabs.tabBar()
        for i, title in enumerate(self._left_titles):      # 전체 이름일 때 필요한 폭을 실제로 잰다
            if bar.tabText(i) != title:
                bar.setTabText(i, title)
        compact = bar.sizeHint().width() + 12 > self.left_tabs.width()
        current = self.left_tabs.currentIndex()
        for i, title in enumerate(self._left_titles):
            text = title if (not compact or i == current) else ""   # 좁으면 선택한 탭만 이름 표시
            if self.left_tabs.tabText(i) != text:
                self.left_tabs.setTabText(i, text)

    def showEvent(self, ev) -> None:  # noqa: N802
        """처음 보일 때 입력 패널 폭을 다시 적용한다 (창이 보이기 전의 setSizes는 실제 폭을 몰라 줄어든다)."""
        super().showEvent(ev)
        if not getattr(self, "_width_applied", False):
            self._width_applied = True
            QTimer.singleShot(0, self._apply_initial_width)

    def _current_panel_width(self) -> int:
        """저장할 입력 패널 폭: 화면에 보이며 폭이 적용된 뒤의 실제 폭, 아니면 의도한 폭."""
        if self._panel_collapsed or not self.isVisible() or not getattr(self, "_width_applied", False):
            return self._panel_width
        return self._main_splitter.sizes()[1] or self._panel_width

    def _apply_initial_width(self) -> None:
        if not self._panel_collapsed and self._main_splitter.sizes()[1] != self._panel_width:
            self.set_panel_width(self._panel_width)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        if hasattr(self, "_command_bar"):
            self._command_bar.update_for_width(self.width())

    # ------------------------------------------------------------------
    # 로그 / 상태
    # ------------------------------------------------------------------

    def log(self, message: str, error: bool = False) -> None:
        """메시지 탭에 시각과 함께 기록하고 상태 표시줄에도 보인다."""
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = "⚠ " if error else ""
        self.log_view.appendPlainText(f"[{stamp}] {prefix}{message}")
        self._status_bar.showMessage(message, 15000 if error else 8000)

    # ------------------------------------------------------------------
    # 스펙트럼 / 시리즈
    # ------------------------------------------------------------------

    def _on_spectrum_loaded(self, spec, title: str) -> None:
        self._analysis.set_spectrum(spec, title)
        if spec is not None:
            self.log(tr("스펙트럼 열기") + f": {title}")

    def _on_open_spectrum(self) -> None:
        self.set_panel_collapsed(False)
        self.left_tabs.setCurrentWidget(self._spectrum_panel)
        self._spectrum_panel._browse()

    def _on_close_spectrum(self) -> None:
        self._spectrum_panel.close_spectrum()

    def _on_pick_peaks(self) -> None:
        if self._spectrum_panel.current_spectrum() is None:
            self.log(tr("먼저 스펙트럼을 여십시오."), error=True)
            return
        self._spectrum_panel.run_peak_picking()

    def _on_preset_applied(self, mass_type: str, tol: float) -> None:
        self._solver_control.set_mass_type(mass_type, tol)
        label = tr("모노이소토픽 (Exact)") if mass_type == "EXACT" else tr("평균 질량 (Average)")
        self.log(tr("측정 모드 프리셋 적용: {m}, 허용 오차 {t} Da", m=label, t=tol))

    def _on_monomers_changed(self) -> None:
        self._update_series()

    def _on_peaks_picked(self, peaks) -> None:
        self._analysis.set_peaks(peaks_to_rows(peaks))
        self._summary_strip.clear()
        self.log(tr("피크 {n}개 검출", n=len(peaks)))

    def _repeat_units(self, mass_type: str) -> dict[str, float]:
        """시리즈 축이 될 반복단위 {이름: 질량} (Block 제외)."""
        units = {}
        for m in self._monomer_panel.get_monomers():
            if m.monomer_type == MonomerType.BLOCK:
                continue
            mass = m.average_mass if mass_type == "AVERAGE" else m.exact_mass
            if mass > 0:
                units[m.name] = mass
        return units

    def _update_series(self) -> None:
        """피크 목록에서 반복단위 간격 시리즈를 검출하고 우세 간격 정보를 표시한다."""
        import numpy as np

        from mpcs.services.series_analysis import find_spacings

        tol, mass_type, _ = self._solver_control.current_settings()
        repeats = self._repeat_units(mass_type)
        min_len, max_gap = self._spectrum_panel.series_options()
        series = self._analysis.update_series(repeats, tol * 1.5, min_len, max_gap)

        pd = self._analysis.to_peak_data()
        if len(pd.mz_values) < 3:
            self._spectrum_panel.set_info("")
            return
        spacings = find_spacings(np.array(sorted(pd.mz_values)), None, bin_da=max(0.02, tol / 2))
        parts = []
        for d, _n in spacings[:3]:
            match = next((k for k, v in repeats.items() if abs(v - d) <= tol * 1.5), None)
            parts.append(f"{d:.3f}" + (f" (= {match})" if match else ""))
        info = tr("피크 {n}개 · 시리즈 {s}개", n=len(pd.mz_values), s=len(series))
        if series:
            info += " — " + ", ".join(x.label() for x in series[:4])
        if parts:
            info += "\n" + tr("우세 간격: {v}", v=", ".join(parts))
        self._spectrum_panel.set_info(info)

    def _sync_poly_from_monomers(self) -> None:
        self._poly_panel.sync_monomers(self._monomer_panel.get_monomers())

    # ------------------------------------------------------------------
    # 프로젝트 UI 동기화
    # ------------------------------------------------------------------

    def _load_project_to_ui(self, open_spectrum: bool = True) -> None:
        self._monomer_panel.load_project(self._project)
        self._constraint_panel.load_project(self._project)
        self._end_group_panel.load_project(self._project)
        self._adduct_panel.load_project(self._project)
        if open_spectrum:
            self._spectrum_panel.close_spectrum()
            if self._project.spectrum_path and Path(self._project.spectrum_path).exists():
                self._spectrum_panel.open_file(self._project.spectrum_path)
        self._analysis.load_peak_data(self._project.peak_data)
        self._summary_strip.clear()
        self._update_series()

    def _collect_project_from_ui(self) -> Project:
        project = self._project
        self._monomer_panel.apply_to_project(project)
        self._constraint_panel.apply_to_project(project)
        self._end_group_panel.apply_to_project(project)
        self._adduct_panel.apply_to_project(project)
        project.peak_data = self._analysis.to_peak_data()
        project.spectrum_path = self._spectrum_panel.file_path()
        return project

    # ------------------------------------------------------------------
    # 파일
    # ------------------------------------------------------------------

    def _project_filter(self) -> str:
        return tr("MPCS 프로젝트") + f" (*{PROJECT_FILE_EXTENSION});;" + tr("모든 파일") + " (*.*)"

    def _on_new_project(self) -> None:
        reply = QMessageBox.question(
            self, tr("새 프로젝트"), tr("현재 프로젝트를 닫고 새 프로젝트를 시작하시겠습니까?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._project = Project()
            self._current_filepath = None
            self._load_project_to_ui()
            self._update_title()
            self.log(tr("새 프로젝트"))

    def _on_open_project(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(self, tr("프로젝트 열기"), str(Path.home()), self._project_filter())
        if filepath:
            self._load_project_file(filepath)

    def _load_project_file(self, filepath: str) -> None:
        try:
            self._project = self._serializer.load(filepath)
            self._current_filepath = filepath
            self._load_project_to_ui()
            self._update_title()
            self._recent_manager.add(filepath)
            self.log(tr("프로젝트 열림: {name}", name=Path(filepath).name))
        except ProjectDeserializeError as exc:
            QMessageBox.critical(self, tr("파일 열기 실패"), tr("프로젝트를 불러올 수 없습니다:\n{e}", e=exc))

    def _on_save_project(self) -> None:
        if self._current_filepath:
            self._save_to_file(self._current_filepath)
        else:
            self._on_save_as_project()

    def _on_save_as_project(self) -> None:
        default_name = f"{self._project.name}{PROJECT_FILE_EXTENSION}"
        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("다른 이름으로 저장"), str(Path.home() / default_name), self._project_filter())
        if filepath:
            if not filepath.endswith(PROJECT_FILE_EXTENSION):
                filepath += PROJECT_FILE_EXTENSION
            self._save_to_file(filepath)

    def _save_to_file(self, filepath: str) -> None:
        project = self._collect_project_from_ui()
        try:
            self._serializer.save(project, filepath)
            self._current_filepath = filepath
            self._recent_manager.add(filepath)
            self._update_title()
            self.log(tr("저장 완료: {name}", name=Path(filepath).name))
        except ProjectSerializeError as exc:
            QMessageBox.critical(self, tr("저장 실패"), tr("프로젝트를 저장할 수 없습니다:\n{e}", e=exc))

    def _on_export_all(self) -> None:
        self._analysis.export_all()

    def _on_export_peak(self) -> None:
        self._analysis._result_view._export_results()

    # ------------------------------------------------------------------
    # 솔버 실행
    # ------------------------------------------------------------------

    def _on_run_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._solver_control._on_run()

    def _on_run_solver(self, tolerance_da: float, mass_type: str, isotope_offset_count: int) -> None:
        project = self._collect_project_from_ui()

        errors = project.validate()
        if errors:
            QMessageBox.warning(
                self, tr("입력 오류"),
                tr("다음 오류를 수정한 후 다시 시도하십시오:") + "\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return

        rows, peaks = self._analysis.solve_targets()
        if not peaks:
            QMessageBox.warning(
                self, tr("피크 없음"),
                tr("오른쪽 피크 목록에 m/z 값을 입력하거나(붙여넣기/가져오기),\n데이터/설정 탭에서 스펙트럼 피크를 검출하십시오."),
            )
            return

        try:
            monomer_names: list[str] = []
            mass_map: dict[str, float] = {}
            for m in project.monomers:
                monomer_names.append(m.name)
                mass_map[m.name] = m.exact_mass
                if m.monomer_type == MonomerType.BLOCK and m.sub_items:
                    for sub in m.sub_items:
                        monomer_names.append(sub.name)
                        mass_map[sub.name] = sub.exact_mass
            parsed = self._engine.parse_all(project.active_constraints(), monomer_names, mass_map)
            self._engine.topological_sort(parsed)
        except CircularDependencyError as exc:
            QMessageBox.critical(
                self, tr("순환 제약식 오류"),
                tr("제약식 간 순환 의존성이 발견되었습니다:\n\n{cycle}\n\n순환 제약식을 수정한 후 다시 시도하십시오.",
                   cycle=" → ".join(exc.cycle)),
            )
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("제약식 오류"), str(exc))
            return

        params = SolverParams(
            peak_mz=peaks[0],
            monomers=project.monomers,
            constraints=project.active_constraints(),
            end_group=project.end_group,
            adducts=project.enabled_adducts(),
            feed_ratio=project.feed_ratio if project.feed_ratio.entries else None,
            sec_data=project.sec_data,
            tolerance_da=tolerance_da,
            mass_type=mass_type,
            isotope_offset_count=isotope_offset_count,
        )

        self._set_running(True)
        self._progress_bar.setRange(0, 0)
        self._analysis.clear_results()
        self._summary_strip.clear()
        self._solve_rows = rows
        self.log(tr("솔버 실행: 피크 {n}개, 허용 오차 {t} Da, {m}", n=len(peaks), t=tolerance_da,
                    m=tr("모노이소토픽 (Exact)") if mass_type == "EXACT" else tr("평균 질량 (Average)")))

        self._worker = BatchSolverWorker(self._solver, peaks, params, list(self._repeat_units(mass_type)))
        self._worker.progress.connect(self._on_solver_progress)
        self._worker.finished.connect(self._on_solver_finished)
        self._worker.error.connect(self._on_solver_error)
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        self.act_run.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self._solver_control.set_running(running)
        self._progress_bar.setVisible(running)
        self._progress_label.setVisible(running)
        if not running:
            self._progress_label.setText("")

    def _on_cancel_solver(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.log(tr("솔버 취소 중..."))

    def _on_solver_progress(self, current, valid_total, all_total) -> None:
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(int(1000 * current / max(all_total, 1)))
        self._progress_label.setText(tr("조합 {c:,} / {a:,} (유효 {v:,})", c=current, a=all_total, v=valid_total))

    def _on_solver_finished(self, results, families) -> None:
        self._set_running(False)
        self._analysis.set_results(self._solve_rows, results, families)
        self._summary_strip.set_result(families, self._analysis.result_summary())
        n_hit = sum(1 for r in results if r.count())
        msg = tr("완료: 피크 {n}개 중 {h}개에서 후보 발견 · 조성 계열 {f}개", n=len(results), h=n_hit, f=len(families))
        if families:
            msg += " — " + tr("최상위: {label} ({n}개 피크)", label=ion_text(families[0].label()), n=families[0].support)
        self.log(msg)

    def _on_solver_error(self, error_msg: str) -> None:
        self._set_running(False)
        self.log(tr("솔버 오류") + f": {error_msg}", error=True)
        QMessageBox.critical(self, tr("솔버 오류"), error_msg)

    # ------------------------------------------------------------------
    # 언어 즉시 전환
    # ------------------------------------------------------------------

    def _capture_state(self) -> dict:
        return {
            "project": self._collect_project_from_ui(),
            "filepath": self._current_filepath,
            "solver": self._solver_control.get_state(),
            "spectrum": self._spectrum_panel.get_state(),
            "analysis": self._analysis.get_state(),
            "families": self._analysis.families(),
            "left_tab": self.left_tabs.currentIndex(),
            "collapsed": self._panel_collapsed,
            "panel_width": self._current_panel_width(),
            "log": self.log_view.toPlainText(),
            "geometry": self.saveGeometry(),
            "maximized": self.isMaximized(),
        }

    def _apply_state(self, st: dict) -> None:
        self._current_filepath = st.get("filepath")
        self._solver_control.set_state(st.get("solver", {}))
        self._spectrum_panel.set_state(st.get("spectrum", {}))
        self._analysis.set_state(st.get("analysis", {}))
        fams = st.get("families") or []
        if any(r.result for r in self._analysis._rows):
            self._summary_strip.set_result(fams, self._analysis.result_summary())
        self.left_tabs.setCurrentIndex(int(st.get("left_tab", 0)))
        self._panel_width = int(st.get("panel_width", self._panel_width))
        sizes = self._main_splitter.sizes()
        self._main_splitter.setSizes([0, self._panel_width, max(sum(sizes) - self._panel_width, 400)])
        if st.get("collapsed"):
            self.set_panel_collapsed(True)
        if st.get("log"):
            self.log_view.setPlainText(st["log"])
        if st.get("geometry") is not None:
            self.restoreGeometry(st["geometry"])

    def request_language_change(self, lang: str):
        """화면 언어를 즉시 바꾼다. 새 창(바꾸지 않았으면 None)을 반환한다."""
        if lang not in ("ko", "en") or lang == current_language():
            return None
        if self._worker is not None and self._worker.isRunning():
            self._command_bar.set_language(current_language())
            self.log(tr("솔버 실행 중에는 화면 언어를 바꿀 수 없습니다."), error=True)
            return None
        state = self._capture_state()
        self._save_window_state()
        I18nManager.get_instance().set_language(lang)
        self._app_config.set_language(lang)
        install_qt_translator(lang)

        new = MainWindow(project=state["project"], recent_manager=self._recent_manager, restore_state=state)
        new.log(tr("화면 언어를 바꿨습니다."))
        if state.get("maximized"):
            new.showMaximized()
        else:
            new.show()
        app = QApplication.instance()
        if app is not None:
            app._mpcs_window = new        # 새 창 참조 유지 (main.py의 지역 변수는 옛 창)
        self.window_replaced.emit(new)
        self.confirm_close = False
        self.hide()
        QTimer.singleShot(0, lambda w=self: (w.close(), _dispose_window(w)))
        return new

    # ------------------------------------------------------------------
    # 창 상태 저장/복원
    # ------------------------------------------------------------------

    def _save_window_state(self) -> None:
        try:
            self._app_config.set("window_geometry", base64.b64encode(bytes(self.saveGeometry())).decode("ascii"))
            self._app_config.set("panel_collapsed", self._panel_collapsed)
            self._app_config.set("input_panel_width", self._current_panel_width())
        except Exception:  # noqa: BLE001 — 설정 저장 실패는 무시
            pass

    def _restore_window_state(self) -> None:
        geo = self._app_config.get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray(base64.b64decode(geo)))
            except Exception:  # noqa: BLE001
                pass
        width = self._app_config.get("input_panel_width")   # 이전 키(panel_width)는 폭 버그로 460이 저장돼 있어 쓰지 않음
        if isinstance(width, int) and width > 300:
            self._panel_width = width
            sizes = self._main_splitter.sizes()
            self._main_splitter.setSizes([0, width, max(sum(sizes) - width, 400)])
        if self._app_config.get("panel_collapsed"):
            self.set_panel_collapsed(True)

    # ------------------------------------------------------------------
    # 기타
    # ------------------------------------------------------------------

    def _on_guide(self) -> None:
        GuideDialog(self).exec()

    def _on_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("MPCS 정보"))
        box.setIconPixmap(app_pixmap(64))
        box.setText(f"<b>{APP_TITLE}</b><br>" + tr("버전 1.3"))
        box.setInformativeText(
            tr("고분자 MALDI·LC-MS 피크의 조성 계산과 조성 계열 분석") + "\n"
            + tr("제작자: Jeonghun Lee (cihkill@gmail.com)") + "\n\nPython 3.12 / PyQt5 (qtpy)"
        )
        box.exec_()

    def _update_title(self) -> None:
        name = Path(self._current_filepath).stem if self._current_filepath else self._project.name
        self.setWindowTitle(f"{name} — {APP_TITLE}")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.confirm_close:
            reply = QMessageBox.question(
                self, tr("종료"), tr("저장하지 않은 변경 사항이 있을 수 있습니다.\n종료하시겠습니까?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._save_window_state()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        event.accept()
