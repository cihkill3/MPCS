"""
MPCS — GUI Panel: Polymerization Calculator (v2.0)
중합 계산기 탭 — 성분 종류별 Carothers 방정식

UI 구조:
    ┌ 성분 종류 수 설정 ─────────────────────────────────────────────┐
    │  종류 수: [2▲▼]  [구성 갱신]                                   │
    └────────────────────────────────────────────────────────────────┘
    ┌ 종류 1: Diol  관능기수: [2]  ──────────────────────────────────┐
    │  ┌ 이름         │ mmol   │ 정밀질량(Da) ┐                       │
    │  │ PEG1000     │ 1.0    │ 1000.0      │                       │
    │  │ BDO         │ 0.5    │  90.1       │                       │
    │  └─────────────┴────────┴─────────────┘                       │
    │  [+ 추가] [- 삭제]      소계: 1.5 mmol | Mn_type = 696 Da     │
    └────────────────────────────────────────────────────────────────┘
    ┌ 종류 2: Diisocyanate  관능기수: [2]  ─────────────────────────┐
    │  ... (동일 구조)                                               │
    └────────────────────────────────────────────────────────────────┘
    ┌ 계산 설정 ─────────────────────────────────────────────────────┐
    │  전환율 p: [0.990]   [▶ 계산]                                  │
    └────────────────────────────────────────────────────────────────┘
    ┌ 계산 결과 ─────────────────────────────────────────────────────┐
    │  f_avg = 2.000 | Xn = 200.0 | Mn = 87,200 Da                 │
    │  ┌ 성분  │ 종류  │ mmol  │ 몰분율  │ 평균개수 │ 질량기여(Da) ┐ │
    │  └───────┴───────┴───────┴─────────┴──────────┴─────────────┘ │
    │  [📋 최소값/최대값 반영...]                                     │
    └────────────────────────────────────────────────────────────────┘

Carothers 방정식:
    f_avg = Σ_all(n_i × f_j) / Σ_all(n_i)
            (f_j: 해당 성분이 속한 종류의 관능기수)
    Xn = 2 / (2 - p × f_avg)     ← p=전환율(0<p≤1)
    겔화점: p_gel = 2 / f_avg

성분별 평균 개수/체인:
    mole_frac_i = n_i / Σ n_j
    avg_count_i = mole_frac_i × Xn
"""

from __future__ import annotations

import math
from typing import NamedTuple

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mpcs.models.monomer import Monomer


# ---------------------------------------------------------------------------
# 내부 데이터 구조
# ---------------------------------------------------------------------------

class ComponentEntry(NamedTuple):
    """성분 1개의 입력 데이터."""
    name: str
    mmol: float
    mw: float       # 정밀질량 (Da)


class TypeResult(NamedTuple):
    """종류별 소계 결과."""
    type_name: str
    functionality: int
    total_mmol: float
    number_avg_mw: float   # Mn_type = Σ(mmol_i * MW_i) / Σ mmol_i


class ComponentResult(NamedTuple):
    """성분별 계산 결과."""
    name: str
    type_name: str
    mmol: float
    mole_frac: float        # 전체 중 몰분율
    avg_count: float        # 체인당 평균 개수 = mole_frac × Xn
    mw: float               # 단위 분자량 (Da)
    mass_contribution: float  # avg_count × mw


# ---------------------------------------------------------------------------
# 성분 종류 그룹 위젯
# ---------------------------------------------------------------------------

_CT_NAME  = 0
_CT_MMOL  = 1
_CT_MW    = 2
_CT_COLS  = 3
_CT_HDRS  = ["성분 이름", "mmol", "정밀질량 (Da)"]


class ComponentTypeGroup(QGroupBox):
    """
    한 가지 성분 종류 입력 위젯.

    예: 종류명="Diol", 관능기수=2, 성분 목록=[PEG1000(1.0, 1000), BDO(0.5, 90)]
    """

    data_changed = Signal()

    def __init__(self, index: int, parent=None) -> None:
        super().__init__(parent)
        self._index = index
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # 종류 헤더 행: 이름 + 그룹 + 관능기수
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel(f"종류 {self._index}  이름:"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("예: Diol, Diisocyanate")
        self._name_edit.setMaximumWidth(120)
        self._name_edit.textChanged.connect(self._refresh_title)
        header_row.addWidget(self._name_edit)

        header_row.addWidget(QLabel(" 반응 그룹:"))
        self._group_combo = QComboBox()
        self._group_combo.addItems(["A", "B"])
        # 종류 인덱스에 따라 기본값 A/B 번갈아 설정
        self._group_combo.setCurrentIndex(0 if self._index % 2 != 0 else 1)
        self._group_combo.currentIndexChanged.connect(lambda _: self.data_changed.emit())
        header_row.addWidget(self._group_combo)

        header_row.addWidget(QLabel(" 관능기수 f:"))
        self._func_spin = QSpinBox()
        self._func_spin.setRange(1, 10)
        self._func_spin.setValue(2)
        self._func_spin.setMaximumWidth(60)
        self._func_spin.valueChanged.connect(lambda _: self.data_changed.emit())
        header_row.addWidget(self._func_spin)
        header_row.addStretch()

        self._subtotal_label = QLabel("소계: -")
        self._subtotal_label.setStyleSheet("color: #0055aa; font-style: italic;")
        header_row.addWidget(self._subtotal_label)
        layout.addLayout(header_row)

        # 성분 테이블
        self._table = QTableWidget(0, _CT_COLS)
        self._table.setHorizontalHeaderLabels(_CT_HDRS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setMaximumHeight(140)
        self._table.setMinimumHeight(80)
        self._table.itemChanged.connect(self._on_table_changed)
        layout.addWidget(self._table)

        # 버튼 행
        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ 성분 추가")
        add_btn.setMaximumWidth(100)
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton("－ 삭제")
        del_btn.setMaximumWidth(80)
        del_btn.clicked.connect(self._del_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._refresh_title()

    def _refresh_title(self) -> None:
        name = self._name_edit.text().strip() or f"종류 {self._index}"
        self.setTitle(name)
        self.data_changed.emit()

    def _on_table_changed(self, _item) -> None:
        self._update_subtotal()
        self.data_changed.emit()

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.blockSignals(True)
        self._table.insertRow(row)
        self._table.setItem(row, _CT_NAME, QTableWidgetItem("성분명"))
        self._table.setItem(row, _CT_MMOL, QTableWidgetItem("1.0"))
        self._table.setItem(row, _CT_MW,   QTableWidgetItem("100.0"))
        self._table.blockSignals(False)
        self._update_subtotal()
        self.data_changed.emit()

    def _del_row(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self._table.removeRow(r)
        self._update_subtotal()
        self.data_changed.emit()

    def _update_subtotal(self) -> None:
        entries = self.get_entries()
        if not entries:
            self._subtotal_label.setText("소계: -")
            return
        total_mmol = sum(e.mmol for e in entries)
        mn_type = (
            sum(e.mmol * e.mw for e in entries) / total_mmol
            if total_mmol > 0 else 0.0
        )
        self._subtotal_label.setText(
            f"소계: {total_mmol:.3f} mmol  |  Mn = {mn_type:,.1f} Da"
        )

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def get_type_name(self) -> str:
        return self._name_edit.text().strip() or f"종류 {self._index}"

    def get_reaction_group(self) -> str:
        return self._group_combo.currentText()

    def get_functionality(self) -> int:
        return self._func_spin.value()

    def get_entries(self) -> list[ComponentEntry]:
        entries = []
        for row in range(self._table.rowCount()):
            try:
                name = self._table.item(row, _CT_NAME).text().strip()
                mmol = float(self._table.item(row, _CT_MMOL).text())
                mw   = float(self._table.item(row, _CT_MW).text())
                if mmol > 0 and name:
                    entries.append(ComponentEntry(name, mmol, mw))
            except (AttributeError, ValueError):
                pass
        return entries

    def set_name(self, name: str) -> None:
        self._name_edit.setText(name)

    def set_reaction_group(self, group: str) -> None:
        idx = self._group_combo.findText(group)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)

    def set_functionality(self, f: int) -> None:
        self._func_spin.setValue(f)

    def add_entry(self, name: str, mmol: float, mw: float) -> None:
        self._table.blockSignals(True)
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, _CT_NAME, QTableWidgetItem(name))
        self._table.setItem(row, _CT_MMOL, QTableWidgetItem(str(mmol)))
        self._table.setItem(row, _CT_MW,   QTableWidgetItem(f"{mw:.4f}"))
        self._table.blockSignals(False)
        self._update_subtotal()


# ---------------------------------------------------------------------------
# 반영 다이얼로그
# ---------------------------------------------------------------------------

class ApplyToleranceDialog(QDialog):
    """
    계산 결과를 min/max에 반영할 때 오차 범위를 묻는 다이얼로그.
    """

    def __init__(self, results: list[ComponentResult], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("최소값/최대값 반영")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("다음 평균 개수를 모노머의 최소값/최대값에 반영합니다:"))

        self._preview = QTableWidget(0, 4)
        self._preview.setHorizontalHeaderLabels(["성분", "평균 개수", "최소값", "최대값"])
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self._preview)

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("오차 범위 (±%):"))
        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.0, 100.0)
        self._tol_spin.setValue(20.0)
        self._tol_spin.setSuffix(" %")
        self._tol_spin.setDecimals(1)
        self._tol_spin.valueChanged.connect(self._update_preview)
        tol_row.addWidget(self._tol_spin)
        tol_row.addStretch()
        layout.addLayout(tol_row)

        hint = QLabel(
            "예: 평균 26.0, 오차 ±20% → 최소값 = 20, 최대값 = 32\n"
            "(min = floor(avg × (1−tol)),  max = ceil(avg × (1+tol)))"
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._results = results
        self._update_preview()

    def _update_preview(self) -> None:
        tol = self._tol_spin.value() / 100.0
        self._preview.setRowCount(0)
        for r in self._results:
            row = self._preview.rowCount()
            self._preview.insertRow(row)
            mn = max(0, math.floor(r.avg_count * (1 - tol)))
            mx = math.ceil(r.avg_count * (1 + tol))
            self._preview.setItem(row, 0, QTableWidgetItem(r.name))
            self._preview.setItem(row, 1, QTableWidgetItem(f"{r.avg_count:.2f}"))
            self._preview.setItem(row, 2, QTableWidgetItem(str(mn)))
            self._preview.setItem(row, 3, QTableWidgetItem(str(mx)))

    @property
    def tolerance_pct(self) -> float:
        return self._tol_spin.value()

    def get_updates(self) -> dict[str, tuple[int, int]]:
        tol = self._tol_spin.value() / 100.0
        return {
            r.name: (
                max(0, math.floor(r.avg_count * (1 - tol))),
                math.ceil(r.avg_count * (1 + tol)),
            )
            for r in self._results
        }


# ---------------------------------------------------------------------------
# 결과 테이블 컬럼
# ---------------------------------------------------------------------------

_RC_NAME   = 0
_RC_TYPE   = 1
_RC_MMOL   = 2
_RC_FRAC   = 3
_RC_COUNT  = 4
_RC_MW     = 5
_RC_MASS   = 6
_RC_COLS   = 7
_RC_HDRS   = ["성분", "종류", "mmol", "몰분율 (%)", "평균 개수/체인", "MW (Da)", "질량 기여 (Da)"]


# ---------------------------------------------------------------------------
# 메인 패널
# ---------------------------------------------------------------------------

class PolymerizationPanel(QWidget):
    """
    중합 계산기 탭 v2.0.

    Signals:
        apply_requested({name: (min, max)}) — MonomerPanel.apply_min_max() 연결
        sync_requested                      — MainWindow에서 모노머 동기화
    """

    apply_requested = Signal(dict)
    sync_requested  = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._type_groups: list[ComponentTypeGroup] = []
        self._calc_results: list[ComponentResult] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── 성분 종류 수 설정 ──────────────────────────────────────────
        ntype_group = QGroupBox("성분 종류 설정")
        ntype_layout = QHBoxLayout(ntype_group)

        ntype_layout.addWidget(QLabel("성분 종류 수:"))
        self._ntype_spin = QSpinBox()
        self._ntype_spin.setRange(1, 8)
        self._ntype_spin.setValue(2)
        self._ntype_spin.setMaximumWidth(70)
        ntype_layout.addWidget(self._ntype_spin)

        refresh_btn = QPushButton("⟳ 구성 갱신")
        refresh_btn.setToolTip(
            "종류 수를 바괶 후 이 버튼을 누르면 입력 영역이 재구성됩니다.\n"
            "(기존 입력은 유지됩니다)"
        )
        refresh_btn.clicked.connect(self._rebuild_type_groups)
        ntype_layout.addWidget(refresh_btn)

        # 모노머 탭에서 가져오기 + 대상 그룹 선택
        sync_btn = QPushButton("⟳ 모노머 탭에서 가져오기")
        sync_btn.setToolTip("모노머 정의 탭의 성분을 선택한 종류로 가져옵니다")
        sync_btn.clicked.connect(self._on_sync_clicked)
        ntype_layout.addWidget(sync_btn)

        ntype_layout.addWidget(QLabel("대상 종류:"))
        self._sync_target_combo = QComboBox()
        self._sync_target_combo.setMinimumWidth(120)
        ntype_layout.addWidget(self._sync_target_combo)
        ntype_layout.addStretch()

        root.addWidget(ntype_group)

        # ── 수직 스플리터: 상단(성분 설정) + 하단(계산 결과) ────────────────
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # ■ 상단 위젯: 성분 종류 입력 영역
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._types_container = QWidget()
        self._types_layout = QVBoxLayout(self._types_container)
        self._types_layout.setSpacing(6)
        self._types_layout.addStretch()
        scroll.setWidget(self._types_container)
        top_layout.addWidget(scroll)

        # 계산 설정 (p 값)
        calc_group = QGroupBox("계산 설정")
        calc_row = QHBoxLayout(calc_group)

        calc_row.addWidget(QLabel("전환율 p (0 < p ≤ 1):"))
        self._p_spin = QDoubleSpinBox()
        self._p_spin.setRange(0.001, 1.000)
        self._p_spin.setValue(0.990)
        self._p_spin.setSingleStep(0.001)
        self._p_spin.setDecimals(3)
        self._p_spin.setMaximumWidth(90)
        self._p_spin.valueChanged.connect(self._update_gel_hint)
        calc_row.addWidget(self._p_spin)

        self._gel_hint = QLabel("")
        self._gel_hint.setStyleSheet("color: #aa4400; font-style: italic;")
        calc_row.addWidget(self._gel_hint)
        calc_row.addStretch()

        calc_btn = QPushButton("▶ 계산")
        calc_btn.setMinimumWidth(90)
        calc_btn.setStyleSheet("font-weight: bold;")
        calc_btn.clicked.connect(self._calculate)
        calc_row.addWidget(calc_btn)

        top_layout.addWidget(calc_group)
        splitter.addWidget(top_widget)

        # ■ 하단 위젯: 계산 결과
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        result_group = QGroupBox("계산 결과")
        result_layout = QVBoxLayout(result_group)

        # 요약
        self._summary_label = QLabel("계산 결과가 없습니다.")
        font = self._summary_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        self._summary_label.setFont(font)
        self._summary_label.setStyleSheet(
            "background: #eef4ff; border: 1px solid #aac; "
            "padding: 4px; border-radius: 3px;"
        )
        result_layout.addWidget(self._summary_label)

        # 종류별 소계 요약
        self._type_summary_label = QLabel()
        self._type_summary_label.setStyleSheet("color: #555; font-size: 11px;")
        self._type_summary_label.setWordWrap(True)
        result_layout.addWidget(self._type_summary_label)

        # 성분별 결과 테이블
        self._result_table = QTableWidget(0, _RC_COLS)
        self._result_table.setHorizontalHeaderLabels(_RC_HDRS)
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._result_table.horizontalHeader().setStretchLastSection(True)
        self._result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._result_table.setAlternatingRowColors(True)
        result_layout.addWidget(self._result_table)

        apply_btn = QPushButton("📋 최소값/최대값에 반영...")
        apply_btn.setToolTip("계산된 평균 개수를 모노머 탭의 최소값/최대값에 자동 설정합니다")
        apply_btn.clicked.connect(self._apply_to_monomers)
        result_layout.addWidget(apply_btn)

        bottom_layout.addWidget(result_group)
        splitter.addWidget(bottom_widget)

        # 스플리터 비율: 상단 70%, 하단 30%
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter)

        # ── 초기 구성 ─────────────────────────────────────────────────
        self._rebuild_type_groups()

    # ------------------------------------------------------------------
    # 종류 그룹 재구성
    # ------------------------------------------------------------------

    def _rebuild_type_groups(self) -> None:
        n_new = self._ntype_spin.value()
        n_old = len(self._type_groups)

        # 기존 그룹 데이터 백업
        old_data: list[tuple[str, str, int, list[ComponentEntry]]] = []
        for g in self._type_groups:
            old_data.append((g.get_type_name(), g.get_reaction_group(), g.get_functionality(), g.get_entries()))

        # 레이아웃에서 모두 제거
        while self._types_layout.count() > 1:
            item = self._types_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._type_groups.clear()

        # 새로 추가
        for i in range(1, n_new + 1):
            grp = ComponentTypeGroup(i, self._types_container)
            grp.data_changed.connect(self._update_gel_hint)
            self._type_groups.append(grp)
            self._types_layout.insertWidget(i - 1, grp)

        # 기존 데이터 복원
        for i, (name, rgroup, func, entries) in enumerate(old_data):
            if i >= len(self._type_groups):
                break
            g = self._type_groups[i]
            g.set_name(name)
            g.set_reaction_group(rgroup)
            g.set_functionality(func)
            for e in entries:
                g.add_entry(e.name, e.mmol, e.mw)

        # 기본값 (새 그룹만)
        for i in range(n_old, len(self._type_groups)):
            g = self._type_groups[i]
            if i == 0:
                g.set_name("A형 (예: Diol)")
                g.set_reaction_group("A")
                g.set_functionality(2)
            elif i == 1:
                g.set_name("B형 (예: Diisocyanate)")
                g.set_reaction_group("B")
                g.set_functionality(2)
            else:
                g.set_name(f"종류 {i + 1}")
                g.set_functionality(2)

        # 동기화 대상 콤보박스 갱신
        self._update_sync_combo()
        self._update_gel_hint()

    # ------------------------------------------------------------------
    # 겔화점 힌트
    # ------------------------------------------------------------------

    def _get_system_params(self) -> tuple[float, float, float, float]:
        """
        시스템의 파라미터를 계산한다.
        Returns:
            (E_A, E_B, N_0, f_eff)
            E_A: A그룹 관능기 당량 합계
            E_B: B그룹 관능기 당량 합계
            N_0: 총 몰수
            f_eff: 유효 관능기수 (2 * min(E_A, E_B) / N_0)
        """
        e_a = 0.0
        e_b = 0.0
        n_0 = 0.0
        for g in self._type_groups:
            f = g.get_functionality()
            rgroup = g.get_reaction_group()
            for e in g.get_entries():
                n_0 += e.mmol
                if rgroup == "A":
                    e_a += e.mmol * f
                else:
                    e_b += e.mmol * f
        
        e_lim = min(e_a, e_b)
        f_eff = (2.0 * e_lim / n_0) if n_0 > 0 else 0.0
        return e_a, e_b, n_0, f_eff

    def _update_gel_hint(self) -> None:
        try:
            e_a, e_b, n_0, f_eff = self._get_system_params()
            if n_0 <= 0 or f_eff <= 0:
                self._gel_hint.setText("")
                return
            
            p_gel = 2.0 / f_eff
            p = self._p_spin.value()
            
            # 당량비 (r)
            e_lim = min(e_a, e_b)
            e_max = max(e_a, e_b)
            r = e_lim / e_max if e_max > 0 else 0.0

            text_parts = [
                f"  r = {r:.3f} (E_A={e_a:.2f}, E_B={e_b:.2f})",
                f"  f_eff = {f_eff:.3f}"
            ]

            if p_gel >= 1.0:
                text_parts.append("겔화 없음 (선형)")
            else:
                warn = "  ⚠ 겔화 초과!" if p >= p_gel else ""
                text_parts.append(f"겔화점 p_gel = {p_gel:.4f}{warn}")
                
            self._gel_hint.setText("  |  ".join(text_parts))
        except Exception:
            self._gel_hint.setText("")

    # ------------------------------------------------------------------
    # 계산
    # ------------------------------------------------------------------

    def _calculate(self) -> None:
        # 1) 입력값 수집
        all_entries: list[tuple[ComponentEntry, str, int]] = []

        for g in self._type_groups:
            entries = g.get_entries()
            if not entries:
                QMessageBox.warning(
                    self, "입력 없음",
                    f"종류 '{g.get_type_name()}'에 성분이 없습니다.\n"
                    "성분을 추가하거나 종류 수를 줄이십시오."
                )
                return
            for e in entries:
                all_entries.append((e, g.get_type_name(), g.get_functionality()))

        e_a, e_b, n_0, f_eff = self._get_system_params()
        if n_0 <= 0:
            QMessageBox.warning(self, "입력 오류", "mmol 합계가 0입니다.")
            return

        # 3) Xn 계산 (Carothers equation for non-stoichiometric mixtures)
        p = self._p_spin.value()
        denom = 2.0 - p * f_eff
        
        p_gel = 2.0 / f_eff if f_eff > 0 else float('inf')
        if p >= p_gel:
            QMessageBox.warning(
                self, "겔화",
                f"현재 조건에서 겔화가 발생합니다.\n"
                f"유효 f_eff = {f_eff:.3f}, 겔화점 p_gel = {p_gel:.4f}\n"
                f"전환율을 낮추거나 당량비(r)를 조절하십시오."
            )
            return
            
        xn = 2.0 / denom

        # 4) 성분별 결과
        comp_results: list[ComponentResult] = []
        for e, type_name, _ in all_entries:
            mole_frac = e.mmol / n_0
            avg_count = mole_frac * xn
            mass_contrib = avg_count * e.mw
            comp_results.append(ComponentResult(
                name=e.name,
                type_name=type_name,
                mmol=e.mmol,
                mole_frac=mole_frac,
                avg_count=avg_count,
                mw=e.mw,
                mass_contribution=mass_contrib,
            ))

        mn = sum(r.mass_contribution for r in comp_results)

        # 5) 종류별 소계
        type_results: list[TypeResult] = []
        for g in self._type_groups:
            entries = g.get_entries()
            tmol = sum(e.mmol for e in entries)
            mn_t = sum(e.mmol * e.mw for e in entries) / tmol if tmol > 0 else 0.0
            type_results.append(TypeResult(
                type_name=g.get_type_name(),
                functionality=g.get_functionality(),
                total_mmol=tmol,
                number_avg_mw=mn_t,
            ))

        # 6) 결과 저장 및 표시
        self._calc_results = comp_results
        self._show_results(comp_results, type_results, f_eff, xn, mn, p)

    def _show_results(
        self,
        comp_results: list[ComponentResult],
        type_results: list[TypeResult],
        f_avg: float,
        xn: float,
        mn: float,
        p: float,
    ) -> None:
        # 요약 레이블
        self._summary_label.setText(
            f"f_avg = {f_avg:.4f}   |   Xn = {xn:.1f}   |   Mn ≈ {mn:,.0f} Da   "
            f"(p = {p:.3f})"
        )

        # 종류별 소계
        parts = []
        for tr in type_results:
            parts.append(
                f"[{tr.type_name}] f={tr.functionality}, "
                f"{tr.total_mmol:.3f} mmol, Mn_type={tr.number_avg_mw:,.1f} Da"
            )
        self._type_summary_label.setText("  |  ".join(parts))

        # 성분별 결과 테이블
        self._result_table.setRowCount(0)
        for r in comp_results:
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)

            def _ri(v, align=Qt.AlignRight | Qt.AlignVCenter):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(align)
                return item

            self._result_table.setItem(row, _RC_NAME,  QTableWidgetItem(r.name))
            self._result_table.setItem(row, _RC_TYPE,  QTableWidgetItem(r.type_name))
            self._result_table.setItem(row, _RC_MMOL,  _ri(f"{r.mmol:.3f}"))
            self._result_table.setItem(row, _RC_FRAC,  _ri(f"{r.mole_frac * 100:.2f}%"))
            self._result_table.setItem(row, _RC_COUNT, _ri(f"{r.avg_count:.2f}"))
            self._result_table.setItem(row, _RC_MW,    _ri(f"{r.mw:.2f}"))
            self._result_table.setItem(row, _RC_MASS,  _ri(f"{r.mass_contribution:,.1f}"))

        self._result_table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # 반영
    # ------------------------------------------------------------------

    def _apply_to_monomers(self) -> None:
        if not self._calc_results:
            QMessageBox.information(self, "결과 없음", "먼저 [▶ 계산]을 실행하십시오.")
            return

        dlg = ApplyToleranceDialog(self._calc_results, self)
        if dlg.exec() == QDialog.Accepted:
            self.apply_requested.emit(dlg.get_updates())

    # ------------------------------------------------------------------
    # 동기화 대상 콤보박스 관리
    # ------------------------------------------------------------------

    def _update_sync_combo(self) -> None:
        """동기화 대상 콤보박스 아이템을 현재 그룹 목록과 동기화한다."""
        current_idx = self._sync_target_combo.currentIndex()
        self._sync_target_combo.blockSignals(True)
        self._sync_target_combo.clear()
        for i, g in enumerate(self._type_groups):
            self._sync_target_combo.addItem(f"종류 {i + 1}: {g.get_type_name()}")
        # 이전 선택 인덱스 복원 (범위 내에서)
        if 0 <= current_idx < self._sync_target_combo.count():
            self._sync_target_combo.setCurrentIndex(current_idx)
        self._sync_target_combo.blockSignals(False)

    def _on_sync_clicked(self) -> None:
        """'모노머 탭에서 가져오기' 버튼 — sync_requested 시그널을 발생시킨다."""
        self.sync_requested.emit()

    # ------------------------------------------------------------------
    # 외부에서 모노머 동기화 (MainWindow에서 호출)
    # ------------------------------------------------------------------

    def sync_monomers(self, monomers: list[Monomer]) -> None:
        """
        MonomerPanel 목록을 사용자가 선택한 종류에 자동 입력한다.

        질량은 effective_mass() 사용 (Block이면 블록 평균 질량).
        대상 그룹은 '대상 종류' 콤보박스에서 선택.
        """
        if not self._type_groups:
            return
        target_idx = self._sync_target_combo.currentIndex()
        if target_idx < 0 or target_idx >= len(self._type_groups):
            target_idx = 0
        g = self._type_groups[target_idx]
        # 기존 행 비우기
        while g._table.rowCount() > 0:
            g._table.removeRow(0)
        for m in monomers:
            g.add_entry(m.name, 1.0, m.effective_mass())
        g._update_subtotal()

