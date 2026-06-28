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

from mpcs.models.constraint import Constraint
from mpcs.models.project import Project


_COLUMNS = ["활성", "제약식"]


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
        super().__init__("제약식", parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 도움말
        hint = QLabel(
            "지원 연산자: + - * / ^ ( ) | 비교: = < <= > >= | 함수: ABS() ROUND() INT()\n"
            "예시: HDI = PLA + SMA - 1  |  EO = 45 * PLA  |  LA >= 10"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 테이블
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 50)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # 입력
        input_layout = QHBoxLayout()
        self._expr_edit = QLineEdit()
        self._expr_edit.setPlaceholderText("제약식 입력 (예: HDI = PLA + SMA - 1)")
        self._expr_edit.returnPressed.connect(self._add_constraint)

        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._add_constraint)
        del_btn = QPushButton("삭제")
        del_btn.clicked.connect(self._delete_selected)

        input_layout.addWidget(QLabel("제약식:"))
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
            QMessageBox.warning(self, "제약식 오류", "\n".join(errors))
            return

        self._append_row(c)
        self._expr_edit.clear()

    def _append_row(self, constraint: Constraint) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        # 활성 체크
        active_item = QTableWidgetItem()
        active_item.setCheckState(Qt.Checked if constraint.is_active else Qt.Unchecked)
        active_item.setFlags(active_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        self._table.setItem(row, 0, active_item)

        expr_item = QTableWidgetItem(constraint.expression)
        self._table.setItem(row, 1, expr_item)

    def _delete_selected(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
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
                c = Constraint(expr_item.text().strip(), is_active=is_active)
                constraints.append(c)
        project.constraints = constraints
