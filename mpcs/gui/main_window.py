"""
MPCS — MALDI Polymer Composition Solver
GUI: Main Window

SRS §4 GUI Layout:
    §4.1 Main Window: Monomer Panel, Constraint Panel, MALDI Input, Result Table
    §4.2 Project Section: New/Open/Save/SaveAs

v1.1 변경:
    - 중합 계산기 탭 추가
    - MonomerPanel ↔ PolymerizationPanel 신호 연결

v1.2 변경:
    - 우측: AnalysisView (스펙트럼 ↔ 피크 목록 ↔ 후보/조성 계열/KMD 연동)
    - 좌측 '스펙트럼' 탭: mzXML 열기, 피크 검출, 주기 시리즈 옵션
    - 여러 피크 일괄 솔버(벡터화) + 연속 반복수 기반 조성 계열 확률
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon, QKeySequence
from qtpy.QtWidgets import (
    QAction,
    QActionGroup,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.mass_calculator import MassCalculator
from mpcs.gui.panels.adduct_panel import AdductPanel
from mpcs.gui.panels.constraint_panel import ConstraintPanel
from mpcs.gui.panels.end_group_panel import EndGroupPanel
from mpcs.gui.panels.monomer_panel import MonomerPanel
from mpcs.gui.panels.polymerization_panel import PolymerizationPanel
from mpcs.gui.panels.solver_control_panel import SolverControlPanel
from mpcs.gui.panels.spectrum_panel import SpectrumPanel, peaks_to_rows
from mpcs.gui.views.analysis_view import AnalysisView
from mpcs.gui.workers.solver_worker import BatchSolverWorker
from mpcs.infrastructure.config_manager import RecentProjectsManager, AppConfigManager
from mpcs.core.i18n import tr
from mpcs.gui.dialogs.guide_dialog import GuideDialog
from mpcs.infrastructure.project_serializer import (
    PROJECT_FILE_EXTENSION,
    ProjectDeserializeError,
    ProjectSerializer,
    ProjectSerializeError,
)
from mpcs.models.monomer import MonomerType
from mpcs.models.project import Project
from mpcs.models.result import PeakData
from mpcs.services.constraint_engine import CircularDependencyError, ConstraintEngine
from mpcs.services.solver_service import SolverParams, SolverService


class MainWindow(QMainWindow):
    """
    MPCS 메인 윈도우.

    SRS §4 GUI Layout 준수.
    Q12: 프로젝트 저장/열기 메뉴 포함.
    v1.1: 중합 계산기 탭 추가.
    """

    def __init__(
        self,
        project: Project | None = None,
        recent_manager: RecentProjectsManager | None = None,
    ) -> None:
        super().__init__()
        # 서비스 초기화
        self._calc = MassCalculator()
        self._engine = ConstraintEngine()
        self._solver = SolverService(self._calc, self._engine)
        self._serializer = ProjectSerializer()
        self._recent_manager = recent_manager or RecentProjectsManager()
        self._app_config = AppConfigManager()
        self._current_filepath: str | None = None
        self._worker: BatchSolverWorker | None = None
        self._solve_rows: list[int] = []

        # 현재 프로젝트
        self._project = project or Project()

        self._setup_ui()
        self._setup_menus()
        self._setup_status_bar()
        self._connect_signals()
        self._load_project_to_ui()
        self._update_title()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("MALDI Polymer Composition Solver")
        self.setMinimumSize(1200, 720)
        self.resize(1450, 860)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # 좌우 분할: 입력 패널 | 결과 패널
        main_splitter = QSplitter(Qt.Horizontal)

        # ── 좌측 탭 패널 ──────────────────────────────────────────────
        left_tabs = QTabWidget()
        left_tabs.setMinimumWidth(520)

        # 탭 1: 모노머
        self._monomer_panel = MonomerPanel(self._calc)
        left_tabs.addTab(self._monomer_panel, "모노머")

        # 탭 2: 제약식
        self._constraint_panel = ConstraintPanel()
        left_tabs.addTab(self._constraint_panel, "제약식")

        # 탭 3: 말단기 / 어덕트
        eg_adduct_widget = QWidget()
        eg_adduct_layout = QVBoxLayout(eg_adduct_widget)
        eg_adduct_layout.setSpacing(8)
        self._end_group_panel = EndGroupPanel()
        self._adduct_panel = AdductPanel()
        eg_adduct_layout.addWidget(self._end_group_panel)
        eg_adduct_layout.addWidget(self._adduct_panel)
        eg_adduct_layout.addStretch()
        left_tabs.addTab(eg_adduct_widget, "말단기 / 어덕트")

        # 탭 4: 스펙트럼 (mzXML → 피크 검출 → 주기 시리즈)
        self._spectrum_panel = SpectrumPanel()
        left_tabs.addTab(self._spectrum_panel, tr("스펙트럼"))

        # 탭 5: 중합 계산기 (신규)
        self._poly_panel = PolymerizationPanel()
        left_tabs.addTab(self._poly_panel, "중합 계산기")

        # 솔버 컨트롤 (탭 아래)
        self._solver_control = SolverControlPanel()
        self._solver_control.run_requested.connect(self._on_run_solver)
        self._solver_control.cancel_requested.connect(self._on_cancel_solver)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(left_tabs)
        left_layout.addWidget(self._solver_control)

        # ── 우측 분석 패널 (피크 목록 ↔ 스펙트럼 ↔ 후보/계열) ───────────
        self._analysis = AnalysisView()

        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(self._analysis)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([520, 730])

        root_layout.addWidget(main_splitter)

    def _connect_signals(self) -> None:
        """패널 간 신호를 연결한다."""
        # 중합 계산기 → MonomerPanel: 최소값/최대값 반영
        self._poly_panel.apply_requested.connect(self._monomer_panel.apply_min_max)

        # 중합 계산기 동기화 버튼 → 현재 모노머 목록 전달
        self._poly_panel.sync_requested.connect(self._sync_poly_from_monomers)

        # 모노머 변경 시 중합 계산기에 자동 알림 (선택 사항)
        self._monomer_panel.monomers_changed.connect(self._on_monomers_changed)

        # 스펙트럼 → 분석 뷰
        self._spectrum_panel.spectrum_loaded.connect(self._analysis.set_spectrum)
        self._spectrum_panel.peaks_picked.connect(self._on_peaks_picked)
        self._spectrum_panel.preset_applied.connect(self._solver_control.set_mass_type)
        self._spectrum_panel.series_options_changed.connect(self._update_series)
        self._analysis.peaks_changed.connect(self._update_series)
        for sig in self._solver_control.settings_changed_signal():
            sig.connect(self._update_series)

    def _on_monomers_changed(self) -> None:
        """모노머 목록 변경 시 시리즈(반복단위 간격) 재검출."""
        self._update_series()

    def _on_peaks_picked(self, peaks) -> None:
        self._analysis.set_peaks(peaks_to_rows(peaks))
        self._status_bar.showMessage(tr("피크 {n}개 검출", n=len(peaks)))

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
        from mpcs.services.series_analysis import find_spacings
        import numpy as np

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
        for d, n in spacings[:3]:
            match = next((k for k, v in repeats.items() if abs(v - d) <= tol * 1.5), None)
            parts.append(f"{d:.3f}" + (f" (= {match})" if match else ""))
        info = tr("피크 {n}개 · 시리즈 {s}개", n=len(pd.mz_values), s=len(series))
        if series:
            info += " — " + ", ".join(x.label() for x in series[:4])
        if parts:
            info += "\n" + tr("우세 간격: ") + ", ".join(parts)
        self._spectrum_panel.set_info(info)

    def _sync_poly_from_monomers(self) -> None:
        """중합 계산기 탭에 현재 모노머 목록을 동기화한다."""
        monomers = self._monomer_panel.get_monomers()
        self._poly_panel.sync_monomers(monomers)

    def _setup_menus(self) -> None:
        """메뉴바 구성 (Q12: 파일 저장/열기 포함)."""
        menubar = self.menuBar()

        # ── 파일 메뉴 ───────────────────────────────────────────────────
        file_menu = menubar.addMenu(tr("파일(&F)"))

        new_action = QAction(tr("새 프로젝트(&N)"), self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_action)

        open_action = QAction(tr("프로젝트 열기(&O)..."), self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction(tr("저장(&S)"), self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction(tr("다른 이름으로 저장(&A)..."), self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._on_save_as_project)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction(tr("종료(&X)"), self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── 설정 메뉴 ───────────────────────────────────────────────────
        settings_menu = menubar.addMenu(tr("설정(&O)"))

        lang_menu = settings_menu.addMenu(tr("언어(&L) / Language"))

        action_ko = QAction(tr("한국어"), self)
        action_ko.setCheckable(True)
        action_ko.setData("ko")

        action_en = QAction(tr("English"), self)
        action_en.setCheckable(True)
        action_en.setData("en")
        
        current_lang = self._app_config.get_language()
        if current_lang == "en":
            action_en.setChecked(True)
        else:
            action_ko.setChecked(True)

        lang_group = QActionGroup(self)
        lang_group.addAction(action_ko)
        lang_group.addAction(action_en)

        lang_menu.addAction(action_ko)
        lang_menu.addAction(action_en)

        def _on_lang_changed(action):
            lang = action.data()
            if lang != self._app_config.get_language():
                self._app_config.set_language(lang)
                QMessageBox.information(
                    self, 
                    "Language Changed", 
                    "언어 설정이 변경되었습니다. 적용하려면 프로그램을 재시작해야 합니다.\n\n"
                    "Language settings have been changed. You must restart the program to apply."
                )

        lang_group.triggered.connect(_on_lang_changed)

        # ── 도움말 메뉴 ─────────────────────────────────────────────────
        help_menu = menubar.addMenu(tr("도움말(&H)"))

        guide_action = QAction(tr("이용 안내(&G) / User Guide"), self)
        guide_action.triggered.connect(self._on_guide)
        help_menu.addAction(guide_action)

        about_action = QAction(tr("정보(&A)..."), self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self) -> None:
        self._status_bar: QStatusBar = self.statusBar()
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimumWidth(500)
        self._progress_bar.setAlignment(Qt.AlignCenter)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                color: #000000;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #a5d8ff;
                border-radius: 3px;
            }
        """)
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("준비")

    # ------------------------------------------------------------------
    # 프로젝트 UI 동기화
    # ------------------------------------------------------------------

    def _load_project_to_ui(self) -> None:
        self._monomer_panel.load_project(self._project)
        self._constraint_panel.load_project(self._project)
        self._end_group_panel.load_project(self._project)
        self._adduct_panel.load_project(self._project)
        self._spectrum_panel.close_spectrum()
        if self._project.spectrum_path and Path(self._project.spectrum_path).exists():
            self._spectrum_panel.open_file(self._project.spectrum_path)
        self._analysis.load_peak_data(self._project.peak_data)
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
    # 파일 메뉴 액션
    # ------------------------------------------------------------------

    def _on_new_project(self) -> None:
        reply = QMessageBox.question(
            self, "새 프로젝트",
            "현재 프로젝트를 닫고 새 프로젝트를 시작하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._project = Project()
            self._current_filepath = None
            self._load_project_to_ui()
            self._update_title()

    def _on_open_project(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "프로젝트 열기",
            str(Path.home()),
            f"MPCS 프로젝트 (*{PROJECT_FILE_EXTENSION});;모든 파일 (*.*)",
        )
        if filepath:
            self._load_project_file(filepath)

    def _load_project_file(self, filepath: str) -> None:
        try:
            project = self._serializer.load(filepath)
            self._project = project
            self._current_filepath = filepath
            self._load_project_to_ui()
            self._update_title()
            self._recent_manager.add(filepath)
            self._status_bar.showMessage(f"프로젝트 열림: {Path(filepath).name}")
        except ProjectDeserializeError as exc:
            QMessageBox.critical(self, "파일 열기 실패", f"프로젝트를 불러올 수 없습니다:\n{exc}")

    def _on_save_project(self) -> None:
        if self._current_filepath:
            self._save_to_file(self._current_filepath)
        else:
            self._on_save_as_project()

    def _on_save_as_project(self) -> None:
        default_name = f"{self._project.name}{PROJECT_FILE_EXTENSION}"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장",
            str(Path.home() / default_name),
            f"MPCS 프로젝트 (*{PROJECT_FILE_EXTENSION});;모든 파일 (*.*)",
        )
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
            self._status_bar.showMessage(f"저장 완료: {Path(filepath).name}")
        except ProjectSerializeError as exc:
            QMessageBox.critical(self, "저장 실패", f"프로젝트를 저장할 수 없습니다:\n{exc}")

    # ------------------------------------------------------------------
    # 솔버 실행
    # ------------------------------------------------------------------

    def _on_run_solver(self, tolerance_da: float, mass_type: str, isotope_offset_count: int) -> None:
        project = self._collect_project_from_ui()

        errors = project.validate()
        if errors:
            QMessageBox.warning(
                self, "입력 오류",
                "다음 오류를 수정한 후 다시 시도하십시오:\n\n"
                + "\n".join(f"• {e}" for e in errors)
            )
            return

        rows, peaks = self._analysis.solve_targets()
        if not peaks:
            QMessageBox.warning(
                self, tr("피크 없음"),
                tr("오른쪽 피크 목록에 m/z 값을 입력하거나(붙여넣기/가져오기),\n스펙트럼 탭에서 피크를 검출하십시오."),
            )
            return

        enabled_adducts = project.enabled_adducts()

        # Q6: 순환 제약식 사전 검증
        try:
            monomer_names = []
            mass_map = {}
            for m in project.monomers:
                monomer_names.append(m.name)
                mass_map[m.name] = m.exact_mass
                if m.monomer_type.value == "Block" and m.sub_items:
                    for sub in m.sub_items:
                        monomer_names.append(sub.name)
                        mass_map[sub.name] = sub.exact_mass

            parsed = self._engine.parse_all(project.active_constraints(), monomer_names, mass_map)
            self._engine.topological_sort(parsed)
        except CircularDependencyError as exc:
            QMessageBox.critical(
                self, "순환 제약식 오류",
                f"제약식 간 순환 의존성이 발견되었습니다:\n\n"
                f"{' → '.join(exc.cycle)}\n\n"
                f"순환 제약식을 수정한 후 다시 시도하십시오."
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "제약식 오류", str(exc))
            return

        params = SolverParams(
            peak_mz=peaks[0],
            monomers=project.monomers,
            constraints=project.active_constraints(),
            end_group=project.end_group,
            adducts=enabled_adducts,
            feed_ratio=project.feed_ratio if project.feed_ratio.entries else None,
            sec_data=project.sec_data,
            tolerance_da=tolerance_da,
            mass_type=mass_type,
            isotope_offset_count=isotope_offset_count,
        )

        self._solver_control.set_running(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._status_bar.showMessage(tr("솔버 실행 중... (피크 {n}개)", n=len(peaks)))
        self._analysis.clear_results()
        self._solve_rows = rows

        repeat_names = list(self._repeat_units(mass_type))
        self._worker = BatchSolverWorker(self._solver, peaks, params, repeat_names)
        self._worker.progress.connect(self._on_solver_progress)
        self._worker.finished.connect(self._on_solver_finished)
        self._worker.error.connect(self._on_solver_error)
        self._worker.start()

    def _on_cancel_solver(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._status_bar.showMessage(tr("솔버 취소 중..."))

    def _on_solver_progress(self, current, valid_total, all_total) -> None:
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(int(1000 * current / max(all_total, 1)))
        self._progress_bar.setFormat(
            f"%p% - {tr('계산한 조합')}: {current:,} / {all_total:,} ({tr('유효')}: {valid_total:,})"
        )

    def _on_solver_finished(self, results, families) -> None:
        self._solver_control.set_running(False)
        self._progress_bar.setVisible(False)
        self._analysis.set_results(self._solve_rows, results, families)
        n_hit = sum(1 for r in results if r.count())
        msg = tr("완료: 피크 {n}개 중 {h}개에서 후보 발견 · 조성 계열 {f}개", n=len(results), h=n_hit, f=len(families))
        if families:
            msg += f" — {tr('최상위')}: {families[0].label()} ({families[0].support} {tr('피크')})"
        self._status_bar.showMessage(msg)

    def _on_solver_error(self, error_msg: str) -> None:
        self._solver_control.set_running(False)
        self._progress_bar.setVisible(False)
        QMessageBox.critical(self, tr("솔버 오류"), error_msg)
        self._status_bar.showMessage(tr("솔버 오류 발생"))

    # ------------------------------------------------------------------
    # 기타
    # ------------------------------------------------------------------

    def _on_guide(self) -> None:
        dlg = GuideDialog(self)
        dlg.exec()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, tr("MPCS 정보"),
            tr("MALDI Polymer Composition Solver\n"
            "버전 1.0\n\n"
            "SRS v1.0 기반 구현\n"
            "제작자: Jeonghun Lee (cihkill@gmail.com)\n\n"
            "Python 3.12 / PyQt5 (qtpy)")
        )

    def _update_title(self) -> None:
        title = "MALDI Polymer Composition Solver"
        if self._current_filepath:
            fname = Path(self._current_filepath).stem
            title = f"{fname} — {title}"
        else:
            title = f"{self._project.name} — {title}"
        self.setWindowTitle(title)

    def closeEvent(self, event) -> None:
        reply = QMessageBox.question(
            self, "종료",
            "저장하지 않은 변경 사항이 있을 수 있습니다.\n종료하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self._worker and self._worker.isRunning():
                self._worker.cancel()
                self._worker.wait(2000)
            event.accept()
        else:
            event.ignore()
