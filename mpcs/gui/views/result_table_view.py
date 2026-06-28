"""
MPCS — GUI View: Result Table View
SRS §18 Results Module

변경사항:
    - 조성 컬럼 → 분자식 컬럼 + 각 모노머별 개수 컬럼으로 동적 분리
    - Probability 컬럼 제거
    - 행 더블클릭 시 분자식이 있으면 동위원소 패턴 다이얼로그 표시
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QAbstractItemView,
    QGroupBox,
    QPushButton,
    QAction,
    QApplication,
)
from qtpy.QtGui import QKeySequence

from mpcs.models.result import RankedResultSet, SolverResult
from mpcs.core.i18n import tr
from mpcs.core.formatting import format_formula_html, format_adduct_html, HtmlDelegate


# ---------------------------------------------------------------------------
# 고정 컬럼 (동적 모노머 컬럼은 display_results에서 삽입됨)
# ---------------------------------------------------------------------------

_FIXED_LEADING = [tr("순위"), tr("분자식")]
_FIXED_TRAILING = [tr("이론 m/z (Da)"), tr("관측 m/z (Da)"), tr("오차 (Da)"), tr("동위원소 오프셋"), tr("어덕트")]


class NumericTableWidgetItem(QTableWidgetItem):
    """숫자 정렬이 가능한 테이블 위젯 아이템."""

    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except ValueError:
            return super().__lt__(other)


class ResultTableView(QGroupBox):
    """
    솔버 결과 테이블.

    표시 규칙:
        - 고정 앞 컬럼: 순위, 분자식
        - 동적 중간 컬럼: 각 모노머 이름 (개수만 표시)
        - 고정 뒤 컬럼: 이론 m/z, 관측 m/z, 오차, 동위원소 오프셋, 어덕트
        - Probability 컬럼 없음
        - 행 더블클릭: 분자식 있으면 동위원소 패턴 다이얼로그
    """

    def __init__(self, parent=None) -> None:
        super().__init__(tr("결과"), parent)
        self._monomer_names: list[str] = []
        self._results_cache: list[SolverResult] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(f"<b>{tr('결과')}</b>")
        self._count_label = QLabel(tr("결과: 0개"))
        self._count_label.setStyleSheet("color: gray; font-size: 11px;")
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self._table = QTableWidget(0, len(_FIXED_LEADING) + len(_FIXED_TRAILING))
        self._table.setHorizontalHeaderLabels(
            _FIXED_LEADING + _FIXED_TRAILING
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)

        layout.addWidget(self._table)

        # 내보내기 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._export_btn = QPushButton("내보내기 (Export)...")
        self._export_btn.clicked.connect(self._export_results)
        btn_layout.addWidget(self._export_btn)
        layout.addLayout(btn_layout)

        # 복사 (Ctrl+C) 액션 추가
        copy_action = QAction(self._table)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self._copy_to_clipboard)
        self._table.addAction(copy_action)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display_results(self, result_set: RankedResultSet) -> None:
        """
        결과를 테이블에 표시한다.
        결과로부터 모노머 이름을 동적으로 추출하여 컬럼을 재구성한다.
        """
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._results_cache = list(result_set.results)

        # 모든 결과에서 모노머 이름 수집 (순서 유지, 첫 등장 순)
        seen: dict[str, None] = {}
        for r in result_set.results:
            for name, _ in r.composition.counts:
                seen.setdefault(name, None)
        self._monomer_names = list(seen.keys())

        # 컬럼 재구성
        total_cols = len(_FIXED_LEADING) + len(self._monomer_names) + len(_FIXED_TRAILING)
        self._table.setColumnCount(total_cols)

        headers = (
            _FIXED_LEADING
            + self._monomer_names
            + _FIXED_TRAILING
        )
        self._table.setHorizontalHeaderLabels(headers)

        # 컬럼 폭 설정
        self._table.setColumnWidth(0, 50)   # 순위
        self._table.setColumnWidth(1, 200)  # 분자식
        mono_start = 2
        for i in range(len(self._monomer_names)):
            self._table.setColumnWidth(mono_start + i, 70)
        trail_start = mono_start + len(self._monomer_names)
        self._table.setColumnWidth(trail_start,     130)  # 이론 m/z
        self._table.setColumnWidth(trail_start + 1, 130)  # 관측 m/z
        self._table.setColumnWidth(trail_start + 2, 90)   # 오차
        self._table.setColumnWidth(trail_start + 3, 110)  # 동위원소 오프셋
        self._table.setColumnWidth(trail_start + 4, 100)  # 어덕트

        for rank, result in enumerate(result_set.results, start=1):
            self._add_row(rank, result)

        self._table.setItemDelegateForColumn(1, HtmlDelegate(self._table, format_formula_html))
        self._table.setItemDelegateForColumn(trail_start + 4, HtmlDelegate(self._table, format_adduct_html))

        self._table.setSortingEnabled(True)
        count = len(result_set.results)
        suffix = tr(" (최대 100개 표시)") if count >= 100 else ""
        self._count_label.setText(tr("결과: {count}개{suffix}", count=count, suffix=suffix))

    def clear(self) -> None:
        """결과를 초기화한다."""
        self._table.setRowCount(0)
        self._monomer_names = []
        self._results_cache = []
        self._count_label.setText(tr("결과: 0개"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_row(self, rank: int, result: SolverResult) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        comp_dict = result.composition.to_dict()
        mono_start = len(_FIXED_LEADING)
        trail_start = mono_start + len(self._monomer_names)

        def _num_item(text: str) -> NumericTableWidgetItem:
            item = NumericTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return item

        def _str_item(text: str) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return item

        # 순위
        self._table.setItem(row, 0, _num_item(str(rank)))

        # 분자식 (None이면 공백). HtmlDelegate가 포매팅을 담당하므로 raw 문자열 저장
        formula_text = result.formula if result.formula else ""
        self._table.setItem(row, 1, _str_item(formula_text))

        # 모노머 개수 컬럼
        for i, name in enumerate(self._monomer_names):
            count = comp_dict.get(name, 0)
            self._table.setItem(row, mono_start + i, _num_item(str(count)))

        # 이론 m/z
        self._table.setItem(row, trail_start,     _num_item(f"{result.calculated_mass:.4f}"))
        # 관측 m/z
        self._table.setItem(row, trail_start + 1, _num_item(f"{result.observed_mass:.4f}"))
        # 오차
        self._table.setItem(row, trail_start + 2, _num_item(f"{result.error_da:.4f}"))
        # 동위원소 오프셋
        self._table.setItem(row, trail_start + 3, _num_item(str(result.isotope_offset)))
        # 어덕트
        self._table.setItem(row, trail_start + 4, _str_item(result.adduct_label))

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self._results_cache):
            return

        result = self._results_cache[row]
        if not result.formula:
            QMessageBox.information(
                self,
                tr("동위원소 패턴"),
                tr("이 후보에는 직접 입력 질량이 포함되어 있어\n분자식을 알 수 없으므로 동위원소 패턴을 계산할 수 없습니다.")
            )
            return

        from mpcs.gui.dialogs.isotope_pattern_dialog import IsotopePatternDialog
        dlg = IsotopePatternDialog(result.formula, result.adduct_label, parent=self)
        dlg.exec_()

    # ------------------------------------------------------------------
    # Export and Copy
    # ------------------------------------------------------------------

    def _copy_to_clipboard(self) -> None:
        selected_rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not selected_rows:
            return

        total_cols = self._table.columnCount()
        lines = []
        
        # Header (index행) 포함
        headers = [self._table.horizontalHeaderItem(c).text() for c in range(total_cols)]
        lines.append("\t".join(headers))

        # 선택된 줄의 전체 데이터 복사
        for row in selected_rows:
            row_data = []
            for col in range(total_cols):
                item = self._table.item(row, col)
                text = item.text() if item else ""
                row_data.append(text)
            lines.append("\t".join(row_data))

        text_to_copy = "\n".join(lines)
        QApplication.clipboard().setText(text_to_copy)

    def _export_results(self) -> None:
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "내보내기", "내보낼 결과가 없습니다.")
            return

        from qtpy.QtWidgets import QFileDialog
        path, filt = QFileDialog.getSaveFileName(
            self,
            "결과 내보내기",
            "",
            "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not path:
            return

        import pandas as pd
        
        total_cols = self._table.columnCount()
        headers = [self._table.horizontalHeaderItem(c).text() for c in range(total_cols)]
        
        data = []
        for r in range(self._table.rowCount()):
            row_data = []
            for c in range(total_cols):
                item = self._table.item(r, c)
                text_val = item.text() if item else ""
                
                # 숫자로 변환 가능한 경우 변환하여 엑셀에서 '텍스트로 저장된 숫자' 오류 방지
                try:
                    # 먼저 정수 변환 시도
                    if '.' not in text_val:
                        val = int(text_val)
                    else:
                        val = float(text_val)
                except ValueError:
                    val = text_val
                    
                row_data.append(val)
            data.append(row_data)

        df = pd.DataFrame(data, columns=headers)
        
        try:
            if path.endswith(".xlsx") or "Excel" in filt:
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "내보내기 완료", f"결과가 성공적으로 저장되었습니다:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "내보내기 오류", f"파일 저장 중 오류가 발생했습니다:\n{e}")
