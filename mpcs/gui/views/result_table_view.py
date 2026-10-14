"""
MPCS — GUI View: Result Table View
SRS §18 Results Module

선택한 피크 1개의 후보 조성 테이블.

컬럼:
    순위 · 확률 · 분자식 · [모노머별 개수...] · 이론 m/z · 관측 m/z · 오차 · 동위원소 오프셋 · 어덕트 · 계열 피크 수
    - 확률: 조성 계열(연속 반복수) 점수 기반 (series_analysis.score_families). 미계산 시 '-'
    - 계열 피크 수: 이 후보와 같은 계열이 설명하는 피크 수

동작:
    - 행 선택 → candidate_selected(SolverResult) 신호 (스펙트럼에서 같은 계열 피크 강조)
    - 행 더블클릭 → 분자식이 있으면 동위원소 패턴 다이얼로그
    - Ctrl+C 복사, 내보내기(xlsx/csv)
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mpcs.core.formatting import HtmlDelegate, format_adduct_html, format_formula_html, ion_text
from mpcs.core.i18n import tr
from mpcs.gui import theme
from mpcs.gui.widgets import fit_header, set_header_tooltips, set_role
from mpcs.models.result import RankedResultSet, SolverResult

N_LEADING = 3
N_TRAILING = 6


def _leading() -> list[str]:
    return [tr("순위"), tr("확률"), tr("분자식")]


def _trailing() -> list[str]:
    return [tr("이론 m/z (Da)"), tr("관측 m/z (Da)"), tr("오차 (Da)"), tr("동위원소 오프셋"), tr("어덕트"), tr("계열 피크 수")]


def _leading_tips() -> list[str]:
    return [
        tr("확률 순위 (같으면 오차가 작은 순)"),
        tr("이 후보가 정답일 확률. 같은 조성 계열(한 반복단위만 1개씩 다른 후보)이 많은 피크를 연속으로 설명할수록 높습니다. "
           "'설명되지 않음' 가능성도 함께 고려합니다."),
        tr("어덕트를 포함한 이온 분자식. 행을 두 번 누르면 동위원소 패턴을 봅니다."),
    ]


def _trailing_tips() -> list[str]:
    return [
        tr("이 조성의 이론 m/z (질량 기준에 따라 모노이소토픽 또는 평균)"),
        tr("관측된 피크 m/z"),
        tr("|관측 − 이론| (Da). 솔버 허용 오차 이하만 후보가 됩니다."),
        tr("0 = 모노이소토픽 피크와 대응, N = N번째 동위원소 피크와 대응"),
        tr("이온화 어덕트"),
        tr("이 후보와 같은 조성 계열이 설명하는 피크 수 (-: 계열 없음)"),
    ]
_ROLE_RESULT = Qt.UserRole + 1
_DISPLAY_LIMIT = 500


class NumericTableWidgetItem(QTableWidgetItem):
    """숫자 정렬이 가능한 테이블 위젯 아이템."""

    def __lt__(self, other):
        try:
            return float(self.text().rstrip("%")) < float(other.text().rstrip("%"))
        except ValueError:
            return super().__lt__(other)


class ResultTableView(QGroupBox):
    """선택한 피크의 솔버 후보 테이블."""

    candidate_selected = Signal(object)   # SolverResult | None

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self._monomer_names: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header_layout = QHBoxLayout()
        self._count_label = QLabel(tr("피크를 선택하면 후보 조성이 표시됩니다"))
        self._count_label.setObjectName("caption")
        header_layout.addWidget(self._count_label)
        header_layout.addStretch()
        self._export_btn = QPushButton(tr("이 피크 내보내기..."))
        self._export_btn.setToolTip(tr("선택한 피크의 후보 표를 엑셀/CSV로 저장합니다."))
        self._export_btn.clicked.connect(self._export_results)
        header_layout.addWidget(self._export_btn)
        layout.addLayout(header_layout)

        self._table = QTableWidget(0, N_LEADING + N_TRAILING)
        self._table.setHorizontalHeaderLabels(_leading() + _trailing())
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self._table)

        copy_action = QAction(self._table)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self._copy_to_clipboard)
        self._table.addAction(copy_action)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display_results(self, result_set: RankedResultSet, title: str | None = None) -> None:
        """후보를 표시한다. 모노머 컬럼은 결과에서 동적으로 구성한다."""
        self._table.blockSignals(True)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        results = result_set.results[:_DISPLAY_LIMIT]
        seen: dict[str, None] = {}
        for r in results:
            for name, _ in r.composition.counts:
                seen.setdefault(name, None)
        self._monomer_names = list(seen.keys())

        headers = _leading() + self._monomer_names + _trailing()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        set_header_tooltips(self._table, _leading_tips()
                            + [tr("이 모노머의 개수") for _ in self._monomer_names] + _trailing_tips())
        widths = [50, 70, 200] + [55] * len(self._monomer_names) + [110, 110, 80, 90, 90, 90]
        for c, w in enumerate(widths):
            self._table.setColumnWidth(c, w)
        fit_header(self._table)

        for rank, result in enumerate(results, start=1):
            self._add_row(rank, result)

        trail = N_LEADING + len(self._monomer_names)
        self._table.setItemDelegateForColumn(2, HtmlDelegate(self._table, format_formula_html))
        self._table.setItemDelegateForColumn(trail + 4, HtmlDelegate(self._table, format_adduct_html))
        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)

        n = result_set.count()
        shown = " " + tr("(상위 {k}개 표시)", k=_DISPLAY_LIMIT) if n > _DISPLAY_LIMIT else ""
        head = title or f"m/z {result_set.peak_mz:.4f}"
        self._count_label.setText(f"<b>{ion_text(head)}</b> — " + tr("후보 {n}개", n=n) + shown)
        set_role(self._count_label, "sectionTitle")
        if results:
            self._table.selectRow(0)

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._monomer_names = []
        self._count_label.setText(tr("피크를 선택하면 후보 조성이 표시됩니다"))
        set_role(self._count_label, "caption")

    def selected_result(self) -> SolverResult | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(_ROLE_RESULT) if item else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_row(self, rank: int, result: SolverResult) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        comp = result.composition.to_dict()
        mono_start = N_LEADING
        trail = mono_start + len(self._monomer_names)

        def num(text: str) -> NumericTableWidgetItem:
            it = NumericTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return it

        def txt(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return it

        rank_item = num(str(rank))
        rank_item.setData(_ROLE_RESULT, result)
        self._table.setItem(row, 0, rank_item)
        prob = result.probability
        self._table.setItem(row, 1, num(f"{prob * 100:.1f}%" if prob is not None else "-"))
        self._table.setItem(row, 2, txt(result.formula or ""))
        for i, name in enumerate(self._monomer_names):
            self._table.setItem(row, mono_start + i, num(str(comp.get(name, 0))))
        self._table.setItem(row, trail, num(f"{result.calculated_mass:.4f}"))
        self._table.setItem(row, trail + 1, num(f"{result.observed_mass:.4f}"))
        self._table.setItem(row, trail + 2, num(f"{result.error_da:.4f}"))
        self._table.setItem(row, trail + 3, num(str(result.isotope_offset)))
        self._table.setItem(row, trail + 4, txt(result.adduct_label))
        sup = result.family_support
        self._table.setItem(row, trail + 5, num(str(sup) if sup and result.family_id else "-"))

    def _on_selection_changed(self) -> None:
        self.candidate_selected.emit(self.selected_result())

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        result = item.data(_ROLE_RESULT) if item else None
        if result is None:
            return
        if not result.formula:
            QMessageBox.information(
                self, tr("동위원소 패턴"),
                tr("이 후보에는 직접 입력 질량이 포함되어 있어\n분자식을 알 수 없으므로 동위원소 패턴을 계산할 수 없습니다."),
            )
            return
        from mpcs.gui.dialogs.isotope_pattern_dialog import IsotopePatternDialog
        IsotopePatternDialog(result.formula, result.adduct_label, parent=self).exec_()

    def _table_rows(self, rows: list[int] | None = None) -> tuple[list[str], list[list]]:
        cols = self._table.columnCount()
        headers = [self._table.horizontalHeaderItem(c).text() for c in range(cols)]
        data = []
        for r in rows if rows is not None else range(self._table.rowCount()):
            data.append([self._table.item(r, c).text() if self._table.item(r, c) else "" for c in range(cols)])
        return headers, data

    def _copy_to_clipboard(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not rows:
            return
        headers, data = self._table_rows(rows)
        QApplication.clipboard().setText("\n".join("\t".join(r) for r in [headers] + data))

    def _export_results(self) -> None:
        if self._table.rowCount() == 0:
            QMessageBox.information(self, tr("내보내기"), tr("내보낼 결과가 없습니다."))
            return
        from qtpy.QtWidgets import QFileDialog
        path, filt = QFileDialog.getSaveFileName(
            self, tr("결과 내보내기"), "", "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not path:
            return
        import pandas as pd

        headers, data = self._table_rows()
        df = pd.DataFrame([[_to_number(v) for v in row] for row in data], columns=headers)
        try:
            if path.endswith(".xlsx") or "Excel" in filt:
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, tr("내보내기 완료"), tr("결과가 성공적으로 저장되었습니다:\n{path}", path=path))
        except Exception as e:
            QMessageBox.critical(self, tr("내보내기 오류"), tr("파일 저장 중 오류가 발생했습니다:\n{e}", e=e))


def _to_number(text: str):
    """엑셀에서 '텍스트로 저장된 숫자'가 되지 않도록 변환."""
    t = text.rstrip("%")
    try:
        return int(t) if "." not in t else float(t)
    except ValueError:
        return text
