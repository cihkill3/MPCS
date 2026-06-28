"""
MPCS — GUI Panels: End Group, Adduct, MALDI Input, Solver Control
SRS §10, §11, §12, §13
Q10: Average Block Mode 변경 시 사용자 확인 다이얼로그
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QRadioButton,
    QCheckBox,
    QButtonGroup,
    QDoubleSpinBox,
    QScrollArea,
)

from mpcs.models.adduct import Adduct, make_default_adducts, parse_adduct_label
from mpcs.models.end_group import EndGroup, DEFAULT_END_GROUPS, parse_end_group_formula
from mpcs.models.project import Project
from mpcs.models.result import PeakData
from mpcs.core.formatting import format_adduct_html, format_formula_html


class HtmlRadioButton(QWidget):
    def __init__(self, html_text, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.btn = QRadioButton()
        self.lbl = QLabel(html_text)
        self.lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.btn)
        layout.addWidget(self.lbl)
        layout.addStretch()
        self.lbl.mousePressEvent = lambda e: self.btn.setChecked(True)

    def isChecked(self):
        return self.btn.isChecked()

    def setChecked(self, state):
        self.btn.setChecked(state)


class HtmlCheckBox(QWidget):
    def __init__(self, html_text, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.cb = QCheckBox()
        self.lbl = QLabel(html_text)
        self.lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.cb)
        layout.addWidget(self.lbl)
        layout.addStretch()
        self.lbl.mousePressEvent = lambda e: self.cb.setChecked(not self.cb.isChecked())

    def isChecked(self):
        return self.cb.isChecked()

    def setChecked(self, state):
        self.cb.setChecked(state)


# =============================================================================
# End Group Panel (SRS §10)
# =============================================================================

class EndGroupPanel(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("말단기 (End Group)", parent)
        self._btn_group = QButtonGroup(self)
        self._entries = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._preset_layout = QVBoxLayout()
        layout.addLayout(self._preset_layout)

        # 사용자 정의 질량 입력
        custom_layout = QHBoxLayout()
        self._custom_rb = QRadioButton("직접 입력 (Da):")
        self._btn_group.addButton(self._custom_rb)
        self._custom_spin = QDoubleSpinBox()
        self._custom_spin.setRange(0.0, 9999.0)
        self._custom_spin.setDecimals(5)
        custom_layout.addWidget(self._custom_rb)
        custom_layout.addWidget(self._custom_spin)
        custom_layout.addStretch()
        layout.addLayout(custom_layout)
        
        self._custom_rb.toggled.connect(self._on_custom_rb_toggled)

        # 기본값 복원 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._restore_btn = QPushButton("기본값 복원")
        self._restore_btn.clicked.connect(self._restore_defaults)
        btn_layout.addWidget(self._restore_btn)
        layout.addLayout(btn_layout)

        self._restore_defaults()

    def _on_custom_rb_toggled(self):
        self._custom_spin.setEnabled(self._custom_rb.isChecked())

    def _create_preset_row(self, formula: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        
        rb = QRadioButton()
        self._btn_group.addButton(rb)
        
        edit = QLineEdit(formula)
        edit.setFixedWidth(150)
        
        lbl = QLabel()
        
        def update_mass():
            try:
                m = parse_end_group_formula(edit.text())
                lbl.setText(f"(mass = {m:.5f} Da)")
                lbl.setStyleSheet("color: black;")
            except Exception as e:
                lbl.setText("(계산 오류)")
                lbl.setStyleSheet("color: red;")
        
        edit.textChanged.connect(update_mass)
        update_mass()
        
        edit.textEdited.connect(lambda: rb.setChecked(True))
        
        row_layout.addWidget(rb)
        row_layout.addWidget(edit)
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        
        self._preset_layout.addWidget(row_widget)
        self._entries.append({'widget': row_widget, 'rb': rb, 'edit': edit})
        return rb

    def _clear_presets(self):
        for e in self._entries:
            self._preset_layout.removeWidget(e['widget'])
            e['widget'].deleteLater()
            self._btn_group.removeButton(e['rb'])
        self._entries.clear()

    def _restore_defaults(self):
        self._clear_presets()
        for formula in DEFAULT_END_GROUPS:
            self._create_preset_row(formula)
        if self._entries:
            self._entries[0]['rb'].setChecked(True)
        self._custom_spin.setValue(0.0)

    def load_project(self, project: Project) -> None:
        eg = project.end_group
        if not eg:
            return
            
        if eg.is_custom_mass:
            self._custom_rb.setChecked(True)
            self._custom_spin.setValue(eg.custom_mass)
        else:
            # 기존 목록에 있으면 선택, 없으면 새로 추가
            found = False
            for e in self._entries:
                if e['edit'].text() == eg.formula:
                    e['rb'].setChecked(True)
                    found = True
                    break
            if not found:
                rb = self._create_preset_row(eg.formula)
                rb.setChecked(True)

    def apply_to_project(self, project: Project) -> None:
        if self._custom_rb.isChecked():
            project.end_group = EndGroup(
                is_custom_mass=True,
                formula="",
                custom_mass=self._custom_spin.value()
            )
            return
            
        for e in self._entries:
            if e['rb'].isChecked():
                project.end_group = EndGroup(
                    is_custom_mass=False,
                    formula=e['edit'].text().strip()
                )
                return
                
        project.end_group = EndGroup()


# =============================================================================
# Adduct Panel (SRS §11)
# =============================================================================

class AdductPanel(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("어덕트 (Adduct)", parent)
        self._entries = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        self._scroll_widget = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.addStretch()
        
        self._scroll_area.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll_area)

        # 버튼 영역
        btn_layout = QHBoxLayout()
        
        self._add_btn = QPushButton("＋ 추가")
        self._add_btn.clicked.connect(lambda: self._add_adduct_row("[M+Na]+", True))
        
        btn_layout.addWidget(self._add_btn)
        btn_layout.addStretch()
        
        self._restore_btn = QPushButton("기본값 복원")
        self._restore_btn.clicked.connect(self._restore_defaults)
        btn_layout.addWidget(self._restore_btn)
        
        layout.addLayout(btn_layout)

        self._restore_defaults()

    def _add_adduct_row(self, label: str, enabled: bool):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        
        cb = QCheckBox()
        cb.setChecked(enabled)
        
        edit = QLineEdit(label)
        edit.setFixedWidth(120)
        
        lbl = QLabel()
        
        def update_mass():
            try:
                exact, avg, z = parse_adduct_label(edit.text())
                lbl.setText(f"(mass = {exact:.5f} Da, z = {z})")
                lbl.setStyleSheet("color: black;")
                cb.setEnabled(True)
            except Exception as e:
                lbl.setText("(계산 오류)")
                lbl.setStyleSheet("color: red;")
                cb.setEnabled(False)
                cb.setChecked(False)
                
        edit.textChanged.connect(update_mass)
        update_mass()
        
        del_btn = QPushButton("X")
        del_btn.setFixedWidth(24)
        del_btn.clicked.connect(lambda: self._remove_row(row_widget))
        
        row_layout.addWidget(cb)
        row_layout.addWidget(edit)
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        row_layout.addWidget(del_btn)
        
        # Insert before the stretch
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, row_widget)
        
        self._entries.append({'widget': row_widget, 'cb': cb, 'edit': edit})

    def _remove_row(self, widget: QWidget):
        for e in self._entries:
            if e['widget'] == widget:
                self._entries.remove(e)
                self._list_layout.removeWidget(widget)
                widget.deleteLater()
                break

    def _clear_all(self):
        for e in list(self._entries):
            self._remove_row(e['widget'])

    def _restore_defaults(self):
        self._clear_all()
        for adduct in make_default_adducts():
            self._add_adduct_row(adduct.label, adduct.enabled)

    def load_project(self, project: Project) -> None:
        if not project.adducts:
            return
        self._clear_all()
        for adduct in project.adducts:
            self._add_adduct_row(adduct.label, adduct.enabled)

    def apply_to_project(self, project: Project) -> None:
        adducts = []
        for e in self._entries:
            label = e['edit'].text().strip()
            if label:
                try:
                    a = Adduct(label=label, enabled=e['cb'].isChecked())
                    adducts.append(a)
                except ValueError:
                    pass
        project.adducts = adducts


# =============================================================================
# MALDI Input Panel (SRS §12)
# =============================================================================

from mpcs.core.i18n import tr

class MaldiInputPanel(QGroupBox):
    """
    MALDI 피크 입력 패널.

    SRS §12 MALDI Data Input:
        §12.1 단일 피크 입력 (m/z 값 직접 입력)
        §12.3 파일에서 가져오기 (탭 구분, Q9)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(tr("MALDI 피크 입력"), parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 단일 m/z 입력
        single_layout = QHBoxLayout()
        self._single_mz_edit = QDoubleSpinBox()
        self._single_mz_edit.setRange(0.0, 9999999.0)
        self._single_mz_edit.setDecimals(4)
        self._single_mz_edit.setSuffix(" Da")
        self._single_mz_edit.setMinimumWidth(150)
        set_btn = QPushButton(tr("단일 피크 설정"))
        set_btn.clicked.connect(self._set_single_peak)

        single_layout.addWidget(QLabel("m/z:"))
        single_layout.addWidget(self._single_mz_edit)
        single_layout.addWidget(set_btn)
        single_layout.addStretch()
        layout.addLayout(single_layout)

        # 파일 가져오기 (Q9)
        file_layout = QHBoxLayout()
        self._file_path_edit = QLineEdit()
        self._file_path_edit.setPlaceholderText(tr("파일 경로 (탭 구분, 헤더 포함)"))
        self._file_path_edit.setReadOnly(True)

        browse_btn = QPushButton(tr("파일 열기..."))
        browse_btn.clicked.connect(self._browse_file)

        file_layout.addWidget(QLabel(tr("피크 파일:")))
        file_layout.addWidget(self._file_path_edit)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # 현재 피크 목록 표시
        layout.addWidget(QLabel(tr("입력된 피크 (m/z):")))
        self._peak_display = QTextEdit()
        self._peak_display.setReadOnly(True)
        self._peak_display.setMaximumHeight(100)
        self._peak_display.setPlaceholderText(tr("m/z 값이 여기에 표시됩니다"))
        layout.addWidget(self._peak_display)

        self._peak_data = PeakData()

    def _set_single_peak(self) -> None:
        mz = self._single_mz_edit.value()
        if mz <= 0.0:
            QMessageBox.warning(self, tr("입력 오류"), tr("m/z 값이 0 이하입니다."))
            return
        self._peak_data = PeakData.single(mz)
        self._update_display()

    def _browse_file(self) -> None:
        from qtpy.QtWidgets import QFileDialog
        from mpcs.infrastructure.file_io import FileImportError, PeakFileIO

        filepath, _ = QFileDialog.getOpenFileName(
            self, tr("피크 파일 열기"), "",
            tr("텍스트 파일 (*.txt *.csv *.xlsx);;모든 파일 (*.*)")
        )
        if filepath:
            try:
                self._peak_data = PeakFileIO.read(filepath)
                self._file_path_edit.setText(filepath)
                self._update_display()
            except FileImportError as exc:
                QMessageBox.critical(self, tr("파일 가져오기 오류"), str(exc))

    def _update_display(self) -> None:
        if self._peak_data.is_empty():
            self._peak_display.clear()
            return
        lines = [
            f"m/z = {mz:.4f} (강도: {int_:.1f})"
            for mz, int_ in zip(
                self._peak_data.mz_values, self._peak_data.intensities
            )
        ]
        self._peak_display.setPlainText("\n".join(lines))

    def load_project(self, project: Project) -> None:
        self._peak_data = project.peak_data
        if not self._peak_data.is_empty():
            self._single_mz_edit.setValue(self._peak_data.mz_values[0])
        self._update_display()

    def apply_to_project(self, project: Project) -> None:
        project.peak_data = self._peak_data


# =============================================================================
# Solver Control Panel (SRS §13)
# =============================================================================

class SolverControlPanel(QWidget):
    """
    솔버 실행 컨트롤 패널.

    Signals:
        run_requested(tolerance_da): 솔버 실행 요청
        cancel_requested(): 솔버 취소 요청
    """

    run_requested = Signal(float, str, int)   # tolerance_da, mass_type, isotope_offset_count
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        from qtpy.QtWidgets import QSpinBox, QComboBox
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("허용 오차:"))
        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.001, 10.0)
        self._tol_spin.setValue(0.05)
        self._tol_spin.setDecimals(3)
        self._tol_spin.setSuffix(" Da")
        self._tol_spin.setMaximumWidth(110)
        layout.addWidget(self._tol_spin)

        layout.addWidget(QLabel("  동위원소 오차 허용 (N):"))
        self._isotope_spin = QSpinBox()
        self._isotope_spin.setRange(0, 10)
        self._isotope_spin.setValue(0)
        self._isotope_spin.setMaximumWidth(60)
        layout.addWidget(self._isotope_spin)

        layout.addWidget(QLabel("  질량 기준:"))
        self._mass_type_combo = QComboBox()
        self._mass_type_combo.addItems(["모노이소토픽 (Exact)", "평균 질량 (Average)"])
        layout.addWidget(self._mass_type_combo)

        layout.addStretch()

        self._run_btn = QPushButton("▶ 솔버 실행")
        self._run_btn.setMinimumWidth(120)
        self._run_btn.clicked.connect(self._on_run)

        self._cancel_btn = QPushButton("■ 취소")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)

        layout.addWidget(self._run_btn)
        layout.addWidget(self._cancel_btn)

    def _on_run(self) -> None:
        mass_type = "EXACT" if self._mass_type_combo.currentIndex() == 0 else "AVERAGE"
        self.run_requested.emit(self._tol_spin.value(), mass_type, self._isotope_spin.value())

    def set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)
        self._cancel_btn.setEnabled(running)
