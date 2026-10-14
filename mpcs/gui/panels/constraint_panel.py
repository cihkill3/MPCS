"""
MPCS — GUI Panel: Constraint Panel
SRS §8 Constraint Module, Q6: 순환 제약식 오류 표시
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mpcs.core.i18n import tr
from mpcs.gui.widgets import caption, set_header_tooltips
from mpcs.models.constraint import Constraint
from mpcs.models.project import Project


class ConstraintPanel(QGroupBox):
    """
    제약식 입력 패널.

    SRS §8 Constraint Module.
    Q6: 순환 제약식은 솔버 실행 시 감지 (MainWindow에서 처리).

    사용 예:
        Constraint 입력: "HDI = PLA + SMA - 1"
        지원 연산자: + - * / ^ ( )
        지원 비교: = < <= > >=
        지원 함수: ABS() ROUND() INT()
    """

    def __init__(self, parent=None) -> None:
        super().__init__(tr("제약식"), parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(caption(tr(
            "모노머 개수 사이의 규칙을 식으로 적어 탐색 범위를 줄입니다. 변수는 모노머 탭의 이름을 그대로 씁니다. "
            "'이름 = 식' 형태의 등식은 그 모노머의 개수를 식으로 계산하므로(탐색에서 제외) 특히 빠릅니다."
        )))
        layout.addWidget(caption(tr(
            "연산자: + - * / ^ ( )   비교: = < <= > >=   함수: ABS() ROUND() INT()   "
            "질량 참조: 이름.mw (예: EO.mw)\n"
            "예: HDI = PLA + SMA - 1   |   EO = 45 * PLA   |   LA >= 10   |   EO * EO.mw <= 3000"
        )))

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels([tr("활성"), tr("제약식")])
        set_header_tooltips(self._table, [
            tr("체크한 제약식만 솔버에 적용됩니다."),
            tr("제약식. 셀을 두 번 눌러 고칠 수 있습니다."),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 60)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self._table)

        input_layout = QHBoxLayout()
        self._expr_edit = QLineEdit()
        self._expr_edit.setPlaceholderText(tr("제약식 입력 (예: HDI = PLA + SMA - 1)"))
        self._expr_edit.setToolTip(tr("제약식을 입력하고 Enter 또는 [추가]를 누르세요."))
        self._expr_edit.returnPressed.connect(self._add_constraint)

        add_btn = QPushButton(tr("추가"))
        add_btn.setToolTip(tr("입력한 제약식을 목록에 추가합니다."))
        add_btn.clicked.connect(self._add_constraint)
        del_btn = QPushButton(tr("삭제"))
        del_btn.setToolTip(tr("선택한 제약식을 지웁니다."))
        del_btn.clicked.connect(self._delete_selected)

        input_layout.addWidget(QLabel(tr("제약식:")))
        input_layout.addWidget(self._expr_edit)
        input_layout.addWidget(add_btn)
        input_layout.addWidget(del_btn)
        layout.addLayout(input_layout)

    def _add_constraint(self) -> None:
        expr = self._expr_edit.text().strip()
        if not expr:
            return
        c = Constraint(expr)
        errors = c.validate()
        if errors:
            QMessageBox.warning(self, tr("제약식 오류"), "\n".join(errors))
            return
        self._append_row(c)
        self._expr_edit.clear()

    def _append_row(self, constraint: Constraint) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        active_item = QTableWidgetItem()
        active_item.setCheckState(Qt.Checked if constraint.is_active else Qt.Unchecked)
        active_item.setFlags(active_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        self._table.setItem(row, 0, active_item)
        self._table.setItem(row, 1, QTableWidgetItem(constraint.expression))

    def _delete_selected(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)

    # ------------------------------------------------------------------
    # Project I/O
    # ------------------------------------------------------------------

    def load_project(self, project: Project) -> None:
        self._table.setRowCount(0)
        for c in project.constraints:
            self._append_row(c)

    def apply_to_project(self, project: Project) -> None:
        constraints: list[Constraint] = []
        for row in range(self._table.rowCount()):
            active_item = self._table.item(row, 0)
            expr_item = self._table.item(row, 1)
            if expr_item:
                is_active = (active_item.checkState() == Qt.Checked) if active_item else True
                constraints.append(Constraint(expr_item.text().strip(), is_active=is_active))
        project.constraints = constraints
