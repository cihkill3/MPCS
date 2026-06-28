"""
MPCS — GUI Panel: Monomer Tree Panel (v2.1)
SRS §5 Monomer Definition Module

변경 이력:
    v2.0: QTableWidget → QTreeWidget 전면 개편
          Block 계층 구조 지원 (Block → SubItem)
          분자식/질량 직접 입력 자동 감지
    v2.1: 기존 항목 수정 기능 추가
          더블클릭 또는 [수정] 버튼으로 편집 모드 진입
"""

from __future__ import annotations

import math
import re

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.formula_parser import FormulaParseError
from mpcs.core.mass_calculator import MassCalculator
from mpcs.models.monomer import (
    BlockSubItem,
    Monomer,
    MonomerType,
    parse_formula_or_mass,
)
from mpcs.models.project import Project


# ---- 이름 검증 유틸리티 --------------------------------------------------

# 성분 이름에 사용 불가한 문자 (SRS §8.3 연산자 + 비교 연산자 + .mw 구분자)
_FORBIDDEN_NAME_RE = re.compile(r'[+*/\^()=<>. ]')
# 이름의 유효 패턴: 영문자·한글·숫자·밑줄만 허용 (선행 숫자 금지)
_VALID_NAME_RE = re.compile(r'^[A-Za-z가-힣_][A-Za-z가-힣0-9_]*$')


def _sanitize_name(name: str) -> str:
    """
    성분 이름에서 하이픈(-)을 밑줄(_)로 자동 변환한다.

    이유: '-' 는 제약식 연산자이므로 이름에 사용하면 파싱 오류 발생.
         EO-LA → EO_LA
    """
    return name.replace('-', '_')


def _validate_name(name: str) -> str | None:
    """
    성분 이름에 지원 연산자가 포함되어 있으면 오류 메시지를 반환한다.

    Returns:
        오류 문자열 (오류 없으면 None)
    """
    forbidden = sorted(set(_FORBIDDEN_NAME_RE.findall(name)))
    if forbidden:
        chars = ', '.join(f"'{c}'" for c in forbidden)
        return (
            f"이름에 연산자 문자가 포함되어 있습니다: {chars}\n"
            f"사용 불가 문자: + * / ^ ( ) = < > . (공백)\n"
            f"하이픈(-)은 밑줄(_)로 자동 변환됩니다."
        )
    return None


# ---------------------------------------------------------------------------
_COL_NAME    = 0
_COL_TYPE    = 1
_COL_FORMULA = 2
_COL_MASS    = 3
_COL_MIN     = 4
_COL_MAX     = 5
_COL_COUNT   = 6

_HEADERS = ["이름", "유형", "분자식 / 질량입력", "정밀질량 (Da)", "최솟값", "최댓값"]

# 최상위 추가 가능 유형
_TOP_TYPES = [
    MonomerType.MONOMER,
    MonomerType.BLOCK,
    MonomerType.CROSSLINKER,
    MonomerType.END_GROUP,
    MonomerType.ADDUCT,
]
# Block 하위에 추가 가능 유형
_SUB_TYPES = [
    MonomerType.MONOMER,
    MonomerType.END_GROUP,
    MonomerType.CROSSLINKER,
]

# 트리 아이템 데이터 역할
_ROLE_DATA     = Qt.UserRole
_ROLE_IS_BLOCK = Qt.UserRole + 1
_ROLE_IS_SUB   = Qt.UserRole + 2

# 색상
_BLOCK_BG = QColor(230, 240, 255)
_SUB_BG   = QColor(245, 248, 255)
_EDIT_BG  = QColor(255, 255, 200)   # 편집 중 강조색


from mpcs.core.i18n import tr

class MonomerPanel(QGroupBox):
    """
    계층형 모노머 정의 패널 (v2.1).

    기능:
        - 일반 모노머/가교제/말단기: 최상위 트리 아이템
        - Block: 최상위 트리 아이템. 하위 성분을 자식으로 가짐
        - 항목 수정: 더블클릭 또는 [수정] 버튼 → 폼에 값 불러오기 → [저장]
        - 분자식 또는 정밀질량 직접 입력 자동 감지
        - name.mw 참조를 위한 mass_map 제공

    Signals:
        monomers_changed: 모노머 목록이 변경될 때마다 발생
    """

    monomers_changed = Signal()

    def __init__(self, mass_calculator: MassCalculator, parent=None) -> None:
        super().__init__(tr("모노머 정의"), parent)
        self._calc = mass_calculator
        self._editing_item: QTreeWidgetItem | None = None   # 현재 편집 중인 아이템
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── 트리 위젯 ─────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(_COL_COUNT)
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setExpandsOnDoubleClick(False)   # 더블클릭 = 편집 (접기/펼치기 비활성)
        
        from mpcs.core.formatting import HtmlDelegate, format_formula_html
        self._tree.setItemDelegateForColumn(_COL_FORMULA, HtmlDelegate(self._tree, format_formula_html))
        header = self._tree.header()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        self._tree.setColumnWidth(_COL_TYPE,    90)
        self._tree.setColumnWidth(_COL_FORMULA, 130)
        self._tree.setColumnWidth(_COL_MASS,    130)
        self._tree.setColumnWidth(_COL_MIN,     60)
        self._tree.setColumnWidth(_COL_MAX,     60)
        layout.addWidget(self._tree, stretch=3)

        # ── 구분선 ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # ── 컨텍스트 레이블 ────────────────────────────────────────────
        self._ctx_label = QLabel()
        self._ctx_label.setStyleSheet(
            "background:#e8f4e8; border:1px solid #9cba9c; "
            "padding:3px; border-radius:3px;"
        )
        self._update_context_label(None)
        layout.addWidget(self._ctx_label)

        # ── 입력 영역 ─────────────────────────────────────────────────
        input_frame = QFrame()
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(4)

        # 행 1: 이름 + 유형
        row1 = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("이름 (예: EO, PLA_PEG_PLA)"))
        self._name_edit.setMinimumWidth(100)
        self._name_edit.textChanged.connect(self._on_name_changed)

        self._type_combo = QComboBox()
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        row1.addWidget(QLabel(tr("이름:")))
        row1.addWidget(self._name_edit, stretch=2)
        row1.addWidget(QLabel(tr("유형:")))
        row1.addWidget(self._type_combo, stretch=1)
        input_layout.addLayout(row1)

        # 행 2: 분자식/질량 (Block일 때 숨김)
        self._formula_row_layout = QHBoxLayout()
        self._formula_edit = QLineEdit()
        self._formula_edit.setPlaceholderText(
            tr("분자식 (예: C2H4O) 또는 정밀질량 (예: 44.026)")
        )
        self._formula_edit.textChanged.connect(self._on_formula_changed)
        self._mass_preview = QLabel(tr("질량: -"))
        self._mass_preview.setMinimumWidth(140)
        self._formula_row_layout.addWidget(QLabel(tr("분자식/질량:")))
        self._formula_row_layout.addWidget(self._formula_edit, stretch=3)
        self._formula_row_layout.addWidget(self._mass_preview)
        self._formula_widget = QWidget()
        self._formula_widget.setLayout(self._formula_row_layout)
        input_layout.addWidget(self._formula_widget)

        # 행 3: 최솟값 + 최댓값 + 버튼
        row3 = QHBoxLayout()
        self._min_label = QLabel(tr("최소값:"))
        self._min_spin = QSpinBox()
        self._min_spin.setRange(0, 99999)
        self._min_spin.setValue(0)
        self._min_spin.setMaximumWidth(80)

        self._max_label = QLabel(tr("최대값:"))
        self._max_spin = QSpinBox()
        self._max_spin.setRange(0, 99999)
        self._max_spin.setValue(100)
        self._max_spin.setMaximumWidth(80)

        self._add_btn = QPushButton(tr("＋ 추가"))
        self._add_btn.clicked.connect(self._on_add_or_save)

        self._edit_btn = QPushButton(tr("✏ 수정"))
        self._edit_btn.clicked.connect(self._start_edit)
        self._edit_btn.setEnabled(False)

        self._cancel_btn = QPushButton(tr("✖ 취소"))
        self._cancel_btn.clicked.connect(self._cancel_edit)
        self._cancel_btn.setVisible(False)

        self._del_btn = QPushButton(tr("－ 삭제"))
        self._del_btn.clicked.connect(self._delete_selected)

        row3.addWidget(self._min_label)
        row3.addWidget(self._min_spin)
        row3.addWidget(self._max_label)
        row3.addWidget(self._max_spin)
        row3.addStretch()
        row3.addWidget(self._add_btn)
        row3.addWidget(self._edit_btn)
        row3.addWidget(self._cancel_btn)
        row3.addWidget(self._del_btn)
        input_layout.addLayout(row3)

        layout.addWidget(input_frame)

        # 초기 유형 콤보 구성
        self._populate_type_combo(sub_mode=False)

    # ------------------------------------------------------------------
    # 유형 콤보 제어
    # ------------------------------------------------------------------

    def _populate_type_combo(self, sub_mode: bool) -> None:
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        types = _SUB_TYPES if sub_mode else _TOP_TYPES
        for t in types:
            self._type_combo.addItem(t.value, t)
        self._type_combo.blockSignals(False)
        self._on_type_changed()

    def _current_type(self) -> MonomerType:
        data = self._type_combo.currentData()
        return data if data is not None else MonomerType.MONOMER

    def _set_type_combo(self, monomer_type: MonomerType) -> None:
        """콤보박스에서 지정된 유형을 선택한다."""
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == monomer_type:
                self._type_combo.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _on_selection_changed(
        self, current: QTreeWidgetItem | None, _previous
    ) -> None:
        # 편집 중이 아닐 때만 컨텍스트 갱신
        if self._editing_item is None:
            is_block_selected = (
                current is not None
                and current.parent() is None
                and current.data(_COL_NAME, _ROLE_IS_BLOCK)
            )
            self._populate_type_combo(sub_mode=is_block_selected)
            self._update_context_label(current)

        # 수정 버튼 활성화: 뭔가 선택됐을 때
        self._edit_btn.setEnabled(
            current is not None and self._editing_item is None
        )

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """더블클릭 시 편집 모드 진입."""
        self._start_edit()

    def _update_context_label(self, item: QTreeWidgetItem | None) -> None:
        if self._editing_item is not None:
            name = self._editing_item.text(_COL_NAME).strip()
            self._ctx_label.setText(f"✏️  편집 중: [{name}] — 수정 후 [저장]을 누르세요")
            self._ctx_label.setStyleSheet(
                "background:#fff8c5; border:1px solid #c8a000; "
                "padding:3px; border-radius:3px; font-weight:bold;"
            )
            return

        self._ctx_label.setStyleSheet(
            "background:#e8f4e8; border:1px solid #9cba9c; "
            "padding:3px; border-radius:3px;"
        )
        if item is None:
            self._ctx_label.setText("ℹ️  선택 없음: 새 항목을 최상위로 추가합니다")
        elif item.data(_COL_NAME, _ROLE_IS_BLOCK):
            name = item.text(_COL_NAME)
            self._ctx_label.setText(
                f"📦  Block 선택됨 [{name}]: 추가 시 이 Block의 하위 성분으로 들어갑니다"
            )
        elif item.data(_COL_NAME, _ROLE_IS_SUB):
            parent_name = item.parent().text(_COL_NAME) if item.parent() else "?"
            self._ctx_label.setText(
                f"🔸  Block 하위 성분 선택됨 (상위: {parent_name})"
            )
        else:
            self._ctx_label.setText(
                "ℹ️  일반 항목 선택됨: 추가 시 최상위로 추가됩니다"
            )

    def _on_name_changed(self, text: str) -> None:
        """-를 _로 자동 변환한다 (커서 위치 유지)."""
        if '-' in text:
            cursor_pos = self._name_edit.cursorPosition()
            sanitized = _sanitize_name(text)
            self._name_edit.blockSignals(True)
            self._name_edit.setText(sanitized)
            self._name_edit.setCursorPosition(cursor_pos)
            self._name_edit.blockSignals(False)

    def _on_type_changed(self) -> None:
        is_block = self._current_type() == MonomerType.BLOCK
        self._formula_widget.setVisible(not is_block)
        if is_block:
            self._min_label.setText("최솟값 (블록 수):")
            self._max_label.setText("최댓값 (블록 수):")
        else:
            self._min_label.setText("최솟값:")
            self._max_label.setText("최댓값:")

    def _on_formula_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._mass_preview.setText("질량: -")
            self._mass_preview.setStyleSheet("")
            return
        try:
            _, mass = parse_formula_or_mass(text, self._calc)
            self._mass_preview.setText(f"질량: {mass:.4f} Da")
            self._mass_preview.setStyleSheet("color: #006600;")
        except Exception:
            self._mass_preview.setText("질량: 오류")
            self._mass_preview.setStyleSheet("color: #cc0000;")

    # ------------------------------------------------------------------
    # 편집 모드
    # ------------------------------------------------------------------

    def _start_edit(self) -> None:
        """선택된 아이템의 값을 입력 폼에 불러와 편집 모드로 진입한다."""
        item = self._tree.currentItem()
        if item is None:
            QMessageBox.information(self, "선택 없음", "수정할 항목을 먼저 선택하십시오.")
            return

        self._editing_item = item
        is_sub = bool(item.data(_COL_NAME, _ROLE_IS_SUB))
        is_block = bool(item.data(_COL_NAME, _ROLE_IS_BLOCK))

        # 유형 콤보 적절한 모드로 전환
        self._type_combo.blockSignals(True)
        if is_sub:
            self._populate_type_combo(sub_mode=True)
        else:
            self._populate_type_combo(sub_mode=False)
        self._type_combo.blockSignals(False)

        # 폼 채우기
        name = item.text(_COL_NAME).strip()
        type_str = item.text(_COL_TYPE).strip()
        formula = item.text(_COL_FORMULA).strip()
        min_val = int(item.text(_COL_MIN)) if item.text(_COL_MIN).strip().isdigit() else 0
        max_val = int(item.text(_COL_MAX)) if item.text(_COL_MAX).strip().isdigit() else 100

        self._name_edit.setText(name)
        try:
            monomer_type = MonomerType(type_str)
            self._set_type_combo(monomer_type)
        except ValueError:
            pass

        if not is_block:
            self._formula_edit.setText(formula)

        self._min_spin.setValue(min_val)
        self._max_spin.setValue(max_val)

        # UI 상태 전환
        self._add_btn.setText("💾 저장")
        self._edit_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._del_btn.setEnabled(False)
        self._tree.setEnabled(False)   # 편집 중 트리 잠금

        # 편집 중 아이템 강조
        for col in range(_COL_COUNT):
            item.setBackground(col, QBrush(_EDIT_BG))

        self._update_context_label(None)

    def _cancel_edit(self) -> None:
        """편집 모드를 취소하고 원래 상태로 복원한다."""
        if self._editing_item is not None:
            self._restore_item_color(self._editing_item)
        self._editing_item = None
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        """편집 모드 UI를 종료한다."""
        self._add_btn.setText("＋ 추가")
        self._edit_btn.setVisible(True)
        self._cancel_btn.setVisible(False)
        self._del_btn.setEnabled(True)
        self._tree.setEnabled(True)
        self._clear_inputs()
        current = self._tree.currentItem()
        self._edit_btn.setEnabled(current is not None)
        self._update_context_label(current)

    def _restore_item_color(self, item: QTreeWidgetItem) -> None:
        """아이템의 배경색을 원래대로 복원한다."""
        is_block = bool(item.data(_COL_NAME, _ROLE_IS_BLOCK))
        is_sub   = bool(item.data(_COL_NAME, _ROLE_IS_SUB))
        if is_block:
            color = _BLOCK_BG
        elif is_sub:
            color = _SUB_BG
        else:
            color = QColor(255, 255, 255)  # 기본 흰색
        for col in range(_COL_COUNT):
            item.setBackground(col, QBrush(color))

    # ------------------------------------------------------------------
    # 추가 / 저장 통합 핸들러
    # ------------------------------------------------------------------

    def _on_add_or_save(self) -> None:
        if self._editing_item is not None:
            self._save_edit()
        else:
            self._add_item()

    def _save_edit(self) -> None:
        """편집 중인 아이템에 폼의 값을 반영하여 저장한다."""
        item = self._editing_item
        if item is None:
            return

        name = _sanitize_name(self._name_edit.text().strip())
        if not name:
            QMessageBox.warning(self, "입력 오류", "이름을 입력하십시오.")
            return

        err = _validate_name(name)
        if err:
            QMessageBox.warning(self, "이름 오류", err)
            return

        monomer_type = self._current_type()
        min_val = self._min_spin.value()
        max_val = self._max_spin.value()

        if min_val > max_val:
            QMessageBox.warning(self, "입력 오류", "최솟값이 최댓값보다 큽니다.")
            return

        is_block = bool(item.data(_COL_NAME, _ROLE_IS_BLOCK))
        is_sub   = bool(item.data(_COL_NAME, _ROLE_IS_SUB))

        if is_block:
            # Block: 이름, min, max만 수정 가능
            item.setText(_COL_NAME, name)
            item.setText(_COL_MIN, str(min_val))
            item.setText(_COL_MAX, str(max_val))
            monomer = item.data(_COL_NAME, _ROLE_DATA)
            if isinstance(monomer, Monomer):
                monomer.name = name
                monomer.min_count = min_val
                monomer.max_count = max_val

        elif is_sub:
            # 하위 성분 수정
            formula_text = self._formula_edit.text().strip()
            if not formula_text:
                QMessageBox.warning(self, "입력 오류", "분자식 또는 정밀질량을 입력하십시오.")
                return
            try:
                formula, exact_mass = parse_formula_or_mass(formula_text, self._calc)
            except Exception as exc:
                QMessageBox.warning(self, "분자식 오류", str(exc))
                return

            item.setText(_COL_NAME,    f"  {name}")
            item.setText(_COL_TYPE,    monomer_type.value)
            item.setText(_COL_FORMULA, formula)
            item.setText(_COL_MASS,    f"{exact_mass:.4f}")
            item.setText(_COL_MIN,     str(min_val))
            item.setText(_COL_MAX,     str(max_val))

            sub = item.data(_COL_NAME, _ROLE_DATA)
            if isinstance(sub, BlockSubItem):
                sub.name = name
                sub.sub_type = monomer_type
                sub.formula_or_mass = formula
                sub.exact_mass = exact_mass
                sub.count_min = min_val
                sub.count_max = max_val

            # 부모 Block 질량 재계산
            if item.parent():
                self._refresh_block_mass(item.parent())

        else:
            # 일반 최상위 모노머 수정
            formula_text = self._formula_edit.text().strip()
            if not formula_text:
                QMessageBox.warning(self, "입력 오류", "분자식 또는 정밀질량을 입력하십시오.")
                return
            try:
                formula, exact_mass = parse_formula_or_mass(formula_text, self._calc)
            except Exception as exc:
                QMessageBox.warning(self, "분자식 오류", str(exc))
                return

            item.setText(_COL_NAME,    name)
            item.setText(_COL_TYPE,    monomer_type.value)
            item.setText(_COL_FORMULA, formula)
            item.setText(_COL_MASS,    f"{exact_mass:.4f}")
            item.setText(_COL_MIN,     str(min_val))
            item.setText(_COL_MAX,     str(max_val))

            monomer = item.data(_COL_NAME, _ROLE_DATA)
            if isinstance(monomer, Monomer):
                monomer.name = name
                monomer.monomer_type = monomer_type
                monomer.formula = formula
                monomer.exact_mass = exact_mass
                monomer.min_count = min_val
                monomer.max_count = max_val

        # 색 복원 후 편집 모드 종료
        self._restore_item_color(item)
        self._editing_item = None
        self._exit_edit_mode()
        self.monomers_changed.emit()

    # ------------------------------------------------------------------
    # 항목 추가 로직
    # ------------------------------------------------------------------

    def _add_item(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 오류", "이름을 입력하십시오.")
            return

        current = self._tree.currentItem()
        monomer_type = self._current_type()

        parent_block_item = self._get_parent_block_item(current)
        if parent_block_item is not None:
            self._add_sub_item(parent_block_item, name, monomer_type)
        else:
            self._add_top_level_item(name, monomer_type)

    def _get_parent_block_item(
        self, current: QTreeWidgetItem | None
    ) -> QTreeWidgetItem | None:
        if current is None:
            return None
        if current.data(_COL_NAME, _ROLE_IS_BLOCK):
            return current
        if current.data(_COL_NAME, _ROLE_IS_SUB):
            return current.parent()
        return None

    def _add_top_level_item(self, name: str, monomer_type: MonomerType) -> None:
        name = _sanitize_name(name)  # - → _ 재확인
        err = _validate_name(name)
        if err:
            QMessageBox.warning(self, "이름 오류", err)
            return

        formula_text = self._formula_edit.text().strip()
        min_count = self._min_spin.value()
        max_count = self._max_spin.value()

        if min_count > max_count:
            QMessageBox.warning(self, "입력 오류", "최솟값이 최댓값보다 큽니다.")
            return

        if monomer_type == MonomerType.BLOCK:
            monomer = Monomer(
                name=name,
                monomer_type=MonomerType.BLOCK,
                formula="~block",
                exact_mass=0.0,
                min_count=min_count,
                max_count=max_count,
                sub_items=[],
            )
        else:
            if not formula_text:
                QMessageBox.warning(self, "입력 오류", "분자식 또는 정밀질량을 입력하십시오.")
                return
            try:
                formula, exact_mass = parse_formula_or_mass(formula_text, self._calc)
            except Exception as exc:
                QMessageBox.warning(self, "입력 오류", str(exc))
                return

            monomer = Monomer(
                name=name,
                monomer_type=monomer_type,
                formula=formula,
                exact_mass=exact_mass,
                min_count=min_count,
                max_count=max_count,
            )

        errors = monomer.validate()
        if errors and monomer_type != MonomerType.BLOCK:
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
            return

        tree_item = self._make_top_level_item(monomer)
        self._tree.addTopLevelItem(tree_item)
        if monomer_type == MonomerType.BLOCK:
            tree_item.setExpanded(True)

        self._clear_inputs()
        self.monomers_changed.emit()

    def _add_sub_item(
        self,
        block_item: QTreeWidgetItem,
        name: str,
        sub_type: MonomerType,
    ) -> None:
        name = _sanitize_name(name)  # - → _ 재확인
        err = _validate_name(name)
        if err:
            QMessageBox.warning(self, "이름 오류", err)
            return

        formula_text = self._formula_edit.text().strip()
        count_min = self._min_spin.value()
        count_max = self._max_spin.value()

        if not formula_text:
            QMessageBox.warning(self, "입력 오류", "분자식 또는 정밀질량을 입력하십시오.")
            return
        if count_min > count_max:
            QMessageBox.warning(self, "입력 오류", "최솟값이 최댓값보다 큽니다.")
            return

        try:
            formula, exact_mass = parse_formula_or_mass(formula_text, self._calc)
        except Exception as exc:
            QMessageBox.warning(self, "분자식 오류", str(exc))
            return

        sub_item = BlockSubItem(
            name=name,
            sub_type=sub_type,
            formula_or_mass=formula,
            exact_mass=exact_mass,
            count_min=count_min,
            count_max=count_max,
        )

        sub_errors = sub_item.validate()
        if sub_errors:
            QMessageBox.warning(self, "입력 오류", "\n".join(sub_errors))
            return

        child = self._make_sub_item(sub_item)
        block_item.addChild(child)
        block_item.setExpanded(True)

        self._refresh_block_mass(block_item)
        self._clear_inputs()
        self.monomers_changed.emit()

    # ------------------------------------------------------------------
    # 트리 아이템 생성
    # ------------------------------------------------------------------

    def _make_top_level_item(self, monomer: Monomer) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        is_block = monomer.monomer_type == MonomerType.BLOCK

        mass_str = f"{monomer.effective_mass():.4f}" if not is_block else "→ 하위에서 계산"
        item.setText(_COL_NAME,    monomer.name)
        item.setText(_COL_TYPE,    monomer.monomer_type.value)
        item.setText(_COL_FORMULA, monomer.formula if not is_block else "")
        item.setText(_COL_MASS,    mass_str)
        item.setText(_COL_MIN,     str(monomer.min_count))
        item.setText(_COL_MAX,     str(monomer.max_count))

        item.setData(_COL_NAME, _ROLE_DATA,     monomer)
        item.setData(_COL_NAME, _ROLE_IS_BLOCK, is_block)
        item.setData(_COL_NAME, _ROLE_IS_SUB,   False)

        if is_block:
            for col in range(_COL_COUNT):
                item.setBackground(col, QBrush(_BLOCK_BG))
            font = item.font(_COL_NAME)
            font.setBold(True)
            item.setFont(_COL_NAME, font)

        for sub in monomer.sub_items:
            child = self._make_sub_item(sub)
            item.addChild(child)

        return item

    def _make_sub_item(self, sub: BlockSubItem) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(_COL_NAME,    f"  {sub.name}")
        item.setText(_COL_TYPE,    sub.sub_type.value)
        item.setText(_COL_FORMULA, sub.formula_or_mass)
        item.setText(_COL_MASS,    f"{sub.exact_mass:.4f}")
        item.setText(_COL_MIN,     str(sub.count_min))
        item.setText(_COL_MAX,     str(sub.count_max))

        item.setData(_COL_NAME, _ROLE_DATA,     sub)
        item.setData(_COL_NAME, _ROLE_IS_BLOCK, False)
        item.setData(_COL_NAME, _ROLE_IS_SUB,   True)

        for col in range(_COL_COUNT):
            item.setBackground(col, QBrush(_SUB_BG))

        return item

    def _refresh_block_mass(self, block_item: QTreeWidgetItem) -> None:
        total = 0.0
        for i in range(block_item.childCount()):
            child = block_item.child(i)
            sub = child.data(_COL_NAME, _ROLE_DATA)
            if isinstance(sub, BlockSubItem):
                total += sub.mass_contribution_avg

        block_item.setText(_COL_MASS, f"{total:.4f} Da (블록)")

        monomer = block_item.data(_COL_NAME, _ROLE_DATA)
        if isinstance(monomer, Monomer):
            monomer.exact_mass = total

    # ------------------------------------------------------------------
    # 삭제
    # ------------------------------------------------------------------

    def _delete_selected(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return

        name = item.text(_COL_NAME).strip()
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"'{name}' 항목을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if item.parent() is None:
            idx = self._tree.indexOfTopLevelItem(item)
            self._tree.takeTopLevelItem(idx)
        else:
            parent = item.parent()
            parent.removeChild(item)
            self._refresh_block_mass(parent)

        self.monomers_changed.emit()

    # ------------------------------------------------------------------
    # 입력 초기화
    # ------------------------------------------------------------------

    def _clear_inputs(self) -> None:
        self._name_edit.clear()
        self._formula_edit.clear()
        self._mass_preview.setText("질량: -")
        self._mass_preview.setStyleSheet("")
        self._min_spin.setValue(0)
        self._max_spin.setValue(100)

    # ------------------------------------------------------------------
    # 공개 API: min/max 일괄 업데이트 (중합 계산기에서 호출)
    # ------------------------------------------------------------------

    def apply_min_max(self, updates: dict[str, tuple[int, int]]) -> None:
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            name = top.text(_COL_NAME)
            if name in updates:
                new_min, new_max = updates[name]
                top.setText(_COL_MIN, str(new_min))
                top.setText(_COL_MAX, str(new_max))
                m = top.data(_COL_NAME, _ROLE_DATA)
                if isinstance(m, Monomer):
                    m.min_count = new_min
                    m.max_count = new_max

            for j in range(top.childCount()):
                child = top.child(j)
                child_name = child.text(_COL_NAME).strip()
                if child_name in updates:
                    new_min, new_max = updates[child_name]
                    child.setText(_COL_MIN, str(new_min))
                    child.setText(_COL_MAX, str(new_max))
                    sub = child.data(_COL_NAME, _ROLE_DATA)
                    if isinstance(sub, BlockSubItem):
                        sub.count_min = new_min
                        sub.count_max = new_max
                    self._refresh_block_mass(top)

        self.monomers_changed.emit()

    # ------------------------------------------------------------------
    # Project I/O
    # ------------------------------------------------------------------

    def load_project(self, project: Project) -> None:
        self._tree.clear()
        for monomer in project.monomers:
            item = self._make_top_level_item(monomer)
            self._tree.addTopLevelItem(item)
            if monomer.monomer_type == MonomerType.BLOCK:
                item.setExpanded(True)
                self._refresh_block_mass(item)

    def apply_to_project(self, project: Project) -> None:
        monomers: list[Monomer] = []
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            monomer = self._extract_monomer(top)
            if monomer:
                monomers.append(monomer)
        project.monomers = monomers

    def _extract_monomer(self, item: QTreeWidgetItem) -> Monomer | None:
        try:
            name = item.text(_COL_NAME).strip()
            monomer_type = MonomerType(item.text(_COL_TYPE).strip())
            formula = item.text(_COL_FORMULA).strip()
            min_count = int(item.text(_COL_MIN))
            max_count = int(item.text(_COL_MAX))

            sub_items: list[BlockSubItem] = []
            if monomer_type == MonomerType.BLOCK:
                for j in range(item.childCount()):
                    child = item.child(j)
                    sub = self._extract_sub_item(child)
                    if sub:
                        sub_items.append(sub)
                exact_mass = sum(s.mass_contribution_avg for s in sub_items) if sub_items else 0.0
            else:
                try:
                    exact_mass = float(item.text(_COL_MASS))
                except ValueError:
                    exact_mass = 0.0

            return Monomer(
                name=name,
                monomer_type=monomer_type,
                formula=formula,
                exact_mass=exact_mass,
                min_count=min_count,
                max_count=max_count,
                sub_items=sub_items,
            )
        except Exception:
            return None

    def _extract_sub_item(self, item: QTreeWidgetItem) -> BlockSubItem | None:
        try:
            name = item.text(_COL_NAME).strip()
            sub_type = MonomerType(item.text(_COL_TYPE).strip())
            formula = item.text(_COL_FORMULA).strip()
            exact_mass = float(item.text(_COL_MASS))
            count_min = int(item.text(_COL_MIN))
            count_max = int(item.text(_COL_MAX))
            return BlockSubItem(
                name=name,
                sub_type=sub_type,
                formula_or_mass=formula,
                exact_mass=exact_mass,
                count_min=count_min,
                count_max=count_max,
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 현재 모노머 목록 조회 (중합 계산기용)
    # ------------------------------------------------------------------

    def get_monomers(self) -> list[Monomer]:
        monomers = []
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            m = self._extract_monomer(top)
            if m:
                monomers.append(m)
        return monomers
