"""
MPCS — GUI Panels: End Group, Adduct, Solver Settings
SRS §10, §11, §13

- EndGroupPanel   말단기 선택 (프리셋 분자식 또는 직접 질량)
- AdductPanel     이온화 어덕트 목록 (켜기/끄기, 추가/삭제)
- SolverControlPanel  솔버 설정 (허용 오차, 질량 기준, 동위원소 오프셋).
  실행/중단 버튼은 메인 윈도우 명령 막대에 있다 (run_requested는 _on_run()으로 보낸다).
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.formatting import format_adduct_html
from mpcs.core.i18n import tr
from mpcs.gui.widgets import caption, set_role
from mpcs.models.adduct import Adduct, make_default_adducts, parse_adduct_label
from mpcs.models.end_group import DEFAULT_END_GROUPS, EndGroup, parse_end_group_formula
from mpcs.models.project import Project


# =============================================================================
# End Group Panel (SRS §10)
# =============================================================================

class EndGroupPanel(QGroupBox):
    """말단기: 고분자 사슬 양 끝에 붙는 원자단. 질량이 모든 후보에 한 번 더해진다."""

    def __init__(self, parent=None) -> None:
        super().__init__(tr("말단기 (End Group)"), parent)
        self._btn_group = QButtonGroup(self)
        self._entries = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(caption(tr(
            "사슬 양 끝에 붙는 원자단을 '/'로 구분해 입력합니다 (예: H/OH = H₂O, OH/OH = H₂O₂). "
            "'Cyclized'는 고리형(말단 없음)입니다. 선택한 말단기의 질량이 모든 후보 조성에 더해집니다."
        )))

        self._preset_layout = QVBoxLayout()
        layout.addLayout(self._preset_layout)

        custom_layout = QHBoxLayout()
        self._custom_rb = QRadioButton(tr("직접 입력 (Da):"))
        self._custom_rb.setToolTip(tr("분자식을 모를 때 말단기 질량을 숫자로 직접 넣습니다. 이 경우 후보의 분자식은 표시되지 않습니다."))
        self._btn_group.addButton(self._custom_rb)
        self._custom_spin = QDoubleSpinBox()
        self._custom_spin.setRange(0.0, 9999.0)
        self._custom_spin.setDecimals(5)
        self._custom_spin.setSuffix(" Da")
        self._custom_spin.setToolTip(tr("말단기 전체 질량 (Da). 정밀질량/평균질량 모드 모두 이 값을 그대로 씁니다."))
        custom_layout.addWidget(self._custom_rb)
        custom_layout.addWidget(self._custom_spin)
        custom_layout.addStretch()
        layout.addLayout(custom_layout)
        self._custom_rb.toggled.connect(self._on_custom_rb_toggled)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._restore_btn = QPushButton(tr("기본값 복원"))
        self._restore_btn.setToolTip(tr("말단기 목록을 기본 프리셋으로 되돌립니다."))
        self._restore_btn.clicked.connect(self._restore_defaults)
        btn_layout.addWidget(self._restore_btn)
        layout.addLayout(btn_layout)

        self._restore_defaults()

    def _on_custom_rb_toggled(self) -> None:
        self._custom_spin.setEnabled(self._custom_rb.isChecked())

    def _create_preset_row(self, formula: str) -> QRadioButton:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        rb = QRadioButton()
        rb.setToolTip(tr("이 말단기를 사용합니다."))
        self._btn_group.addButton(rb)

        edit = QLineEdit(formula)
        edit.setFixedWidth(150)
        edit.setPlaceholderText("H/OH")
        edit.setToolTip(tr("말단기 분자식. 양 끝을 '/'로 구분합니다 (예: H/OH, NH2/OH, Cyclized)."))

        lbl = QLabel()

        def update_mass() -> None:
            try:
                m = parse_end_group_formula(edit.text())
                lbl.setText(tr("(질량 = {m:.5f} Da)", m=m))
                set_role(lbl, "caption")
            except Exception:  # noqa: BLE001
                lbl.setText(tr("(계산 오류)"))
                set_role(lbl, "errorText")

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

    def _clear_presets(self) -> None:
        for e in self._entries:
            self._preset_layout.removeWidget(e['widget'])
            e['widget'].deleteLater()
            self._btn_group.removeButton(e['rb'])
        self._entries.clear()

    def _restore_defaults(self) -> None:
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
            return
        for e in self._entries:
            if e['edit'].text() == eg.formula:
                e['rb'].setChecked(True)
                return
        self._create_preset_row(eg.formula).setChecked(True)

    def apply_to_project(self, project: Project) -> None:
        if self._custom_rb.isChecked():
            project.end_group = EndGroup(is_custom_mass=True, formula="", custom_mass=self._custom_spin.value())
            return
        for e in self._entries:
            if e['rb'].isChecked():
                project.end_group = EndGroup(is_custom_mass=False, formula=e['edit'].text().strip())
                return
        project.end_group = EndGroup()


# =============================================================================
# Adduct Panel (SRS §11)
# =============================================================================

class AdductPanel(QGroupBox):
    """이온화 어덕트: 체크한 어덕트마다 후보 m/z를 계산한다."""

    def __init__(self, parent=None) -> None:
        super().__init__(tr("어덕트 (Adduct)"), parent)
        self._entries = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(caption(tr(
            "이온화될 때 붙거나 떨어지는 이온입니다. '[M+Na]+', '[M+2H]2+', '[M-H]-' 형식으로 입력하면 "
            "질량과 전하(z)를 자동 계산합니다 (전자 질량 보정 포함). 체크한 어덕트만 솔버가 사용합니다."
        )))

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.NoFrame)
        self._scroll_widget = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.addStretch()
        self._scroll_area.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll_area)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton(tr("＋ 추가"))
        self._add_btn.setToolTip(tr("어덕트 행을 추가합니다. 레이블을 고쳐 원하는 이온으로 바꾸세요."))
        self._add_btn.clicked.connect(lambda: self._add_adduct_row("[M+Na]+", True))
        btn_layout.addWidget(self._add_btn)
        btn_layout.addStretch()
        self._restore_btn = QPushButton(tr("기본값 복원"))
        self._restore_btn.setToolTip(tr("어덕트 목록을 기본값으로 되돌립니다 ([M+Na]+만 켜짐)."))
        self._restore_btn.clicked.connect(self._restore_defaults)
        btn_layout.addWidget(self._restore_btn)
        layout.addLayout(btn_layout)

        self._restore_defaults()

    def _add_adduct_row(self, label: str, enabled: bool) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)

        cb = QCheckBox()
        cb.setChecked(enabled)
        cb.setToolTip(tr("체크하면 솔버가 이 어덕트로 후보 m/z를 계산합니다."))

        edit = QLineEdit(label)
        edit.setFixedWidth(120)
        edit.setPlaceholderText("[M+Na]+")
        edit.setToolTip(tr("어덕트 레이블. 예: [M+H]+, [M+Na]+, [M+K]+, [M+NH4]+, [M+2Na]2+, [M-H]-"))

        preview = QLabel()
        preview.setTextFormat(Qt.RichText)
        preview.setMinimumWidth(80)
        preview.setToolTip(tr("표시 형식 (전하는 위첨자)"))
        lbl = QLabel()

        def update_mass() -> None:
            try:
                exact, _avg, z = parse_adduct_label(edit.text())
                preview.setText(format_adduct_html(edit.text().strip()))
                lbl.setText(tr("(질량 = {m:.5f} Da, z = {z})", m=exact, z=z))
                set_role(lbl, "caption")
                cb.setEnabled(True)
            except Exception:  # noqa: BLE001
                preview.setText("")
                lbl.setText(tr("(계산 오류)"))
                set_role(lbl, "errorText")
                cb.setEnabled(False)
                cb.setChecked(False)

        edit.textChanged.connect(update_mass)
        update_mass()

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(30)
        del_btn.setToolTip(tr("이 어덕트를 목록에서 지웁니다."))
        del_btn.clicked.connect(lambda: self._remove_row(row_widget))

        row_layout.addWidget(cb)
        row_layout.addWidget(edit)
        row_layout.addWidget(preview)
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        row_layout.addWidget(del_btn)

        self._list_layout.insertWidget(self._list_layout.count() - 1, row_widget)
        self._entries.append({'widget': row_widget, 'cb': cb, 'edit': edit})

    def _remove_row(self, widget: QWidget) -> None:
        for e in self._entries:
            if e['widget'] == widget:
                self._entries.remove(e)
                self._list_layout.removeWidget(widget)
                widget.deleteLater()
                break

    def _clear_all(self) -> None:
        for e in list(self._entries):
            self._remove_row(e['widget'])

    def _restore_defaults(self) -> None:
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
                    adducts.append(Adduct(label=label, enabled=e['cb'].isChecked()))
                except ValueError:
                    pass
        project.adducts = adducts


# =============================================================================
# Solver Settings (SRS §13)
# =============================================================================

class SolverControlPanel(QGroupBox):
    """
    솔버 설정 (데이터/설정 탭).

    Signals:
        run_requested(tolerance_da, mass_type, isotope_offset_count): 솔버 실행 요청 (_on_run)
        cancel_requested(): 솔버 취소 요청
    """

    run_requested = Signal(float, str, int)
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(tr("솔버 설정"), parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._mass_type_combo = QComboBox()
        self._mass_type_combo.addItem(tr("모노이소토픽 (Exact)"))
        self._mass_type_combo.addItem(tr("평균 질량 (Average)"))
        self._mass_type_combo.setToolTip(tr(
            "Exact: 동위원소가 분리되는 Reflectron / 고분해능 LC-MS. 모노이소토픽 정밀질량으로 비교합니다.\n"
            "Average: 동위원소가 분리되지 않는 Linear 모드(고분자량). 평균 질량으로 비교합니다."
        ))
        self._mass_type_combo.currentIndexChanged.connect(self._on_mass_type_changed)
        form.addRow(tr("질량 기준"), self._mass_type_combo)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.001, 10.0)
        self._tol_spin.setValue(0.05)
        self._tol_spin.setDecimals(3)
        self._tol_spin.setSingleStep(0.01)
        self._tol_spin.setSuffix(" Da")
        self._tol_spin.setToolTip(tr(
            "관측 m/z와 이론 m/z의 최대 허용 차이 (Da). 이 범위 안의 조성만 후보가 됩니다.\n"
            "권장: Reflectron·LC-MS 0.01–0.05 Da, Linear 0.5–2 Da. 주기 시리즈 검출에도 쓰입니다."
        ))
        form.addRow(tr("허용 오차"), self._tol_spin)

        self._isotope_spin = QSpinBox()
        self._isotope_spin.setRange(0, 10)
        self._isotope_spin.setValue(0)
        self._isotope_spin.setToolTip(tr(
            "관측 피크가 모노이소토픽이 아니라 N번째 동위원소(+1.00335·N/z Da)일 가능성까지 허용합니다.\n"
            "0 = 모노이소토픽만. 평균 질량 모드에서는 쓰지 않습니다."
        ))
        form.addRow(tr("동위원소 오프셋 (N)"), self._isotope_spin)

        form.addRow(caption(tr(
            "스펙트럼 탭의 측정 모드 프리셋(Reflectron / Linear)을 누르면 질량 기준과 허용 오차가 함께 맞춰집니다. "
            "솔버 실행은 명령 막대의 [솔버 실행] (F5)."
        )))

    def _on_mass_type_changed(self, index: int) -> None:
        """평균 질량 모드: 동위원소 오프셋 비활성화, 허용 오차가 너무 작으면 Linear 모드 기본값(1 Da)으로."""
        is_average = index == 1
        self._isotope_spin.setEnabled(not is_average)
        if is_average and self._tol_spin.value() < 0.5:
            self._tol_spin.setValue(1.0)

    def _on_run(self) -> None:
        self.run_requested.emit(*self.current_settings())

    def current_settings(self) -> tuple[float, str, int]:
        """(허용 오차 Da, 'EXACT'|'AVERAGE', 동위원소 오프셋 수)."""
        mass_type = "EXACT" if self._mass_type_combo.currentIndex() == 0 else "AVERAGE"
        return self._tol_spin.value(), mass_type, self._isotope_spin.value()

    def set_mass_type(self, mass_type: str, tolerance_da: float | None = None) -> None:
        """스펙트럼 프리셋(Reflectron/Linear)에서 질량 기준과 허용 오차를 맞춘다."""
        self._mass_type_combo.setCurrentIndex(0 if mass_type == "EXACT" else 1)
        if tolerance_da is not None:
            self._tol_spin.setValue(tolerance_da)

    def settings_changed_signal(self):
        """허용 오차/질량 기준 변경 신호 목록 (시리즈 재검출용)."""
        return [self._tol_spin.valueChanged, self._mass_type_combo.currentIndexChanged]

    def set_running(self, running: bool) -> None:
        """실행 중에는 설정을 바꾸지 못하게 한다."""
        for w in (self._mass_type_combo, self._tol_spin):
            w.setEnabled(not running)
        self._isotope_spin.setEnabled(not running and self._mass_type_combo.currentIndex() == 0)

    def get_state(self) -> dict:
        return {"mass_type": self._mass_type_combo.currentIndex(), "tol": self._tol_spin.value(),
                "iso": self._isotope_spin.value()}

    def set_state(self, state: dict) -> None:
        self._mass_type_combo.setCurrentIndex(int(state.get("mass_type", 0)))
        self._tol_spin.setValue(float(state.get("tol", 0.05)))
        self._isotope_spin.setValue(int(state.get("iso", 0)))
