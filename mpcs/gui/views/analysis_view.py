"""
MPCS — GUI View: Analysis View (피크 목록 ↔ 스펙트럼 ↔ 후보 / 조성 계열)

레이아웃 (세로 분할):
    ┌ 스펙트럼 플롯 (스펙트럼을 연 경우에만) ────────────────┐
    │  피크 클릭 → 피크 선택, 선택 후보의 계열 피크를 ▲와 n 라벨로 강조 │
    ├ 피크 목록 (마스터) ─────────────────────────────────────┤
    │  질량값 직접 입력/붙여넣기/엑셀 가져오기 또는 피크 검출 결과       │
    ├ 상세 탭 ────────────────────────────────────────────────┤
    │  [후보 조성] 선택 피크의 후보 (확률, 계열 피크 수)                │
    │  [조성 계열] 연속 반복수로 많은 피크를 설명하는 계열 순위          │
    │  [KMD]       Kendrick mass defect 플롯                         │
    └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QBrush, QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.formatting import ion_text
from mpcs.core.i18n import tr
from mpcs.gui import theme
from mpcs.gui.widgets import caption, fit_header, role_label, set_header_tooltips
from mpcs.gui.views.result_table_view import NumericTableWidgetItem, ResultTableView
from mpcs.models.result import PeakData, RankedResultSet, SolverResult
from mpcs.models.spectrum import Spectrum
from mpcs.services.series_analysis import (
    CompositionFamily,
    PeakSeries,
    detect_series,
    kendrick_mass_defect,
)

pg.setConfigOptions(antialias=True, background=theme.SURFACE, foreground=theme.TEXT_2)

HIGHLIGHT_COLOR = theme.FAMILY_HL
SELECT_COLOR = theme.ACCENT

# 피크 목록 컬럼
C_USE, C_MZ, C_INT, C_SNR, C_SERIES, C_NCAND, C_BEST, C_PROB, C_ADDUCT, C_FAM, C_NOTE = range(11)


def _peak_headers() -> list[str]:
    return [tr("사용"), "m/z", tr("강도"), "S/N", tr("시리즈"), tr("후보 수"), tr("최상위 조성"), tr("확률"),
            tr("어덕트"), tr("계열 피크"), tr("메모")]


def _peak_header_tips() -> list[str]:
    return [
        tr("체크한 피크만 솔버에 넣습니다."),
        tr("관측 m/z. 질량 목록 모드에서는 셀을 두 번 눌러 고칠 수 있습니다."),
        tr("피크 강도 (스펙트럼에서 검출한 경우 스무딩 후 높이)."),
        tr("신호 대 잡음비 (스펙트럼에서 검출한 경우)."),
        tr("이 피크가 속한 주기 시리즈 (반복단위 간격으로 이어진 피크 묶음)."),
        tr("허용 오차 안에 든 후보 조성 수."),
        tr("확률이 가장 높은 후보 조성."),
        tr("최상위 후보의 확률. 같은 계열이 많은 피크를 연속으로 설명할수록 높습니다."),
        tr("최상위 후보의 어덕트."),
        tr("최상위 후보와 같은 조성 계열이 설명하는 피크 수."),
        tr("메모 (가져온 파일의 설명 열, 동위원소 묶음 크기 등). 두 번 눌러 고칠 수 있습니다."),
    ]


@dataclass
class PeakRow:
    mz: float
    intensity: float | None = None
    snr: float | None = None
    enabled: bool = True
    note: str = ""
    series_ids: list[int] = field(default_factory=list)
    result: RankedResultSet | None = None


# ---------------------------------------------------------------------------
# 스펙트럼 플롯
# ---------------------------------------------------------------------------

class SpectrumPlot(pg.PlotWidget):
    """스펙트럼 + 검출 피크 + 선택/계열 강조. 클릭하면 가장 가까운 피크를 선택한다."""

    peak_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setLabel("bottom", "m/z")
        self.setLabel("left", "Intensity")
        self.showGrid(x=True, y=True, alpha=0.15)
        self.setMouseEnabled(x=True, y=False)
        self.getPlotItem().getViewBox().setLimits(yMin=0)
        self._curve = self.plot(pen=pg.mkPen(theme.SPECTRUM_LINE, width=1))
        self._curve.setDownsampling(auto=True, method="peak")
        self._curve.setClipToView(True)
        self._peaks = pg.ScatterPlotItem(size=7, pen=None)
        self._family = pg.ScatterPlotItem(size=13, symbol="t1", pen=pg.mkPen(theme.SURFACE), brush=pg.mkBrush(HIGHLIGHT_COLOR))
        self._selected = pg.ScatterPlotItem(size=16, symbol="o", pen=pg.mkPen(SELECT_COLOR, width=2), brush=None)
        self._sel_line = pg.InfiniteLine(angle=90, pen=pg.mkPen(SELECT_COLOR, width=1, style=Qt.DashLine))
        self._sel_line.setVisible(False)
        for item in (self._peaks, self._family, self._selected, self._sel_line):
            self.addItem(item)
        self._labels: list[pg.TextItem] = []
        self._peak_mz = np.zeros(0)
        self._peak_y = np.zeros(0)
        self.scene().sigMouseClicked.connect(self._on_click)

    def set_spectrum(self, spec: Spectrum | None) -> None:
        if spec is None:
            self._curve.setData([], [])
            return
        if spec.centroided:
            x = np.repeat(spec.mz, 3)
            y = np.zeros_like(x)
            y[1::3] = spec.intensity
            self._curve.setData(x, y, connect="all")
        else:
            self._curve.setData(spec.mz, spec.intensity)
        self.getPlotItem().enableAutoRange()

    def set_peaks(self, mz: np.ndarray, y: np.ndarray, colors: list[str]) -> None:
        self._peak_mz, self._peak_y = np.asarray(mz, float), np.asarray(y, float)
        self._peaks.setData(x=self._peak_mz, y=self._peak_y * 1.02,
                            brush=[pg.mkBrush(c) for c in colors], symbol="o")

    def set_selected(self, idx: int | None) -> None:
        if idx is None or idx >= self._peak_mz.size:
            self._selected.setData([], [])
            self._sel_line.setVisible(False)
            return
        x, y = self._peak_mz[idx], self._peak_y[idx]
        self._selected.setData([x], [y * 1.02])
        self._sel_line.setPos(x)
        self._sel_line.setVisible(True)
        vb = self.getPlotItem().getViewBox()
        (x0, x1), _ = vb.viewRange()
        if not (x0 <= x <= x1):
            w = x1 - x0
            vb.setXRange(x - w / 2, x + w / 2, padding=0)

    def set_family(self, indices: list[int], labels: list[str]) -> None:
        for t in self._labels:
            self.removeItem(t)
        self._labels = []
        idx = [i for i in indices if i < self._peak_mz.size]
        if not idx:
            self._family.setData([], [])
            return
        ymax = float(self._peak_y.max()) if self._peak_y.size else 1.0
        xs, ys = self._peak_mz[idx], self._peak_y[idx] + ymax * 0.05
        self._family.setData(xs, ys)
        if len(idx) <= 120:
            for x, y, lab in zip(xs, ys, [labels[indices.index(i)] for i in idx]):
                t = pg.TextItem(lab, color=HIGHLIGHT_COLOR, anchor=(0.5, 1.2))
                t.setPos(x, y)
                self.addItem(t)
                self._labels.append(t)

    def _on_click(self, ev) -> None:
        if ev.button() != Qt.LeftButton or self._peak_mz.size == 0:
            return
        vb = self.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(ev.scenePos()):
            return
        p = vb.mapSceneToView(ev.scenePos())
        (x0, x1), _ = vb.viewRange()
        tol = (x1 - x0) * 0.015
        near = np.nonzero(np.abs(self._peak_mz - p.x()) <= tol)[0]
        if near.size:
            # 가까운 후보 중 강도가 큰 피크 우선 (작은 노이즈 피크 오선택 방지)
            score = np.abs(self._peak_mz[near] - p.x()) / tol - self._peak_y[near] / max(self._peak_y[near].max(), 1e-12)
            self.peak_clicked.emit(int(near[np.argmin(score)]))


# ---------------------------------------------------------------------------
# KMD 플롯
# ---------------------------------------------------------------------------

class KmdPanel(QWidget):
    peak_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("기준 반복단위:")))
        top.addSpacing(4)
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._redraw)
        self._combo.setToolTip(tr("KMD 계산에 쓸 반복단위. 이 단위의 정수배만큼 떨어진 피크는 같은 KMD를 갖습니다."))
        top.addWidget(self._combo)
        top.addWidget(caption(tr(
            "Kendrick mass defect: KMD = round(KM) − KM, KM = m/z × round(M)/M. 같은 계열은 수평선 위에 정렬됩니다. "
            "점을 클릭하면 피크가 선택됩니다.")), 1)
        top.addStretch()
        lay.addLayout(top)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "m/z")
        self._plot.setLabel("left", "Kendrick mass defect")
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._scatter = pg.ScatterPlotItem(size=8, pen=None)
        self._scatter.sigClicked.connect(self._on_points_clicked)
        self._plot.addItem(self._scatter)
        lay.addWidget(self._plot)
        self._repeats: dict[str, float] = {}
        self._mz = np.zeros(0)
        self._colors: list[str] = []

    def set_data(self, repeats: dict[str, float], mz: np.ndarray, colors: list[str]) -> None:
        current = self._combo.currentText()
        self._repeats, self._mz, self._colors = repeats, np.asarray(mz, float), colors
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(list(repeats))
        if current in repeats:
            self._combo.setCurrentText(current)
        self._combo.blockSignals(False)
        self._redraw()

    def _redraw(self) -> None:
        name = self._combo.currentText()
        if not name or self._mz.size == 0:
            self._scatter.setData([], [])
            return
        kmd = kendrick_mass_defect(self._mz, self._repeats[name])
        self._scatter.setData(x=self._mz, y=kmd, data=list(range(self._mz.size)),
                              brush=[pg.mkBrush(c) for c in self._colors])

    def _on_points_clicked(self, _item, points, *_args) -> None:
        if len(points):
            self.peak_clicked.emit(int(points[0].data()))


# ---------------------------------------------------------------------------
# Analysis View
# ---------------------------------------------------------------------------

class AnalysisView(QWidget):
    """피크 목록(마스터) + 스펙트럼 + 후보/계열(디테일)."""

    peaks_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[PeakRow] = []
        self._series: list[PeakSeries] = []
        self._families: list[CompositionFamily] = []
        self._family_by_id: dict[int, CompositionFamily] = {}
        self._solved_rows: list[int] = []
        self._highlight_rows: set[int] = set()
        self._spectrum: Spectrum | None = None
        self._repeats: dict[str, float] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(Qt.Vertical)

        # 스펙트럼
        self._spec_box = QWidget()
        sb = QVBoxLayout(self._spec_box)
        sb.setContentsMargins(0, 0, 0, 0)
        self._spec_title = caption("", wrap=False)
        self._spec_title.setContentsMargins(4, 2, 4, 2)
        sb.addWidget(self._spec_title)
        self._plot = SpectrumPlot()
        self._plot.peak_clicked.connect(self.select_peak)
        self._plot.setToolTip(tr(
            "피크(●)를 누르면 선택됩니다. 색 = 주기 시리즈, ▲와 숫자 = 선택한 후보와 같은 조성 계열의 피크와 반복 수.\n"
            "마우스 휠: 확대/축소 · 드래그: 이동 · 오른쪽 버튼: 보기 메뉴"))
        sb.addWidget(self._plot)
        self._spec_box.setVisible(False)
        self._splitter.addWidget(self._spec_box)

        # 피크 목록
        peak_box = QWidget()
        pb = QVBoxLayout(peak_box)
        pb.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(role_label(tr("피크 목록"), "panelTitle"))
        for text, slot, tip in [
            (tr("가져오기..."), self._import_file, tr("엑셀/CSV/TXT의 m/z(, 강도, 메모) 열을 읽습니다")),
            (tr("붙여넣기"), self._paste, tr("엑셀에서 복사한 셀을 붙여넣습니다 (Ctrl+V)")),
            (tr("행 추가"), self._add_row, tr("빈 행을 추가하고 m/z를 바로 입력합니다.")),
            (tr("선택 삭제"), self._delete_selected, tr("선택한 피크 행을 지웁니다.")),
            (tr("모두 지우기"), self._clear_rows, tr("피크 목록을 모두 지웁니다.")),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            bar.addWidget(b)
        bar.addStretch()
        pb.addLayout(bar)
        bar = QHBoxLayout()
        self._series_only = QCheckBox(tr("주기 시리즈 피크만"))
        self._series_only.setToolTip(tr("반복단위 간격으로 이어지는 시리즈에 속한 피크만 표시하고 솔버에 사용합니다"))
        self._series_only.toggled.connect(self._apply_filter)
        bar.addWidget(self._series_only)
        self._peak_count = caption("", wrap=False)
        self._peak_count.setToolTip(tr("전체 피크 수 · 솔버에 들어갈 피크 수 · 주기 시리즈 수"))
        bar.addWidget(self._peak_count)
        bar.addStretch()
        self._export_all_btn = QPushButton(tr("전체 결과 내보내기..."))
        self._export_all_btn.setToolTip(tr("피크 요약 · 전체 후보 · 조성 계열을 엑셀(.xlsx) 시트 3개로 저장합니다."))
        self._export_all_btn.clicked.connect(self.export_all)
        bar.addWidget(self._export_all_btn)
        pb.addLayout(bar)

        self._table = QTableWidget(0, len(_peak_headers()))
        self._table.setHorizontalHeaderLabels(_peak_headers())
        set_header_tooltips(self._table, _peak_header_tips())
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        for c, w in zip(range(11), [48, 95, 80, 55, 70, 64, 220, 60, 90, 76, 120]):
            self._table.setColumnWidth(c, w)
        fit_header(self._table)
        self._table.itemSelectionChanged.connect(self._on_table_selection)
        self._table.itemChanged.connect(self._on_item_changed)
        pb.addWidget(self._table)
        self._splitter.addWidget(peak_box)

        # 상세 탭
        self._tabs = QTabWidget()
        self._result_view = ResultTableView()
        self._result_view.candidate_selected.connect(self._on_candidate_selected)
        self._tabs.addTab(self._result_view, tr("후보 조성"))

        fam_box = QWidget()
        fb = QVBoxLayout(fam_box)
        fb.setContentsMargins(4, 4, 4, 4)
        fb.addWidget(caption(tr(
            "같은 계열 = 반복단위 하나만 연속으로 증가하고 나머지 조성·어덕트가 같은 후보들. "
            "많은 피크를 연속적으로, 작은 오차로 설명할수록 점수가 높습니다. 행을 고르면 그 계열의 피크가 강조됩니다.")))
        self._fam_table = QTableWidget(0, 8)
        self._fam_table.setHorizontalHeaderLabels([
            tr("순위"), tr("조성 계열"), tr("설명 피크 수"), tr("최장 연속"), tr("n 범위"),
            tr("평균 |오차| (Da)"), tr("점수"), tr("평균 확률")])
        set_header_tooltips(self._fam_table, [
            tr("점수 순위"),
            tr("반복단위 n=범위 · 고정 조성 · 어덕트 (동위원소 오프셋이 있으면 +N iso)"),
            tr("이 계열의 후보가 있는 피크 수"),
            tr("반복 수 n이 끊김 없이 이어지는 가장 긴 구간의 피크 수"),
            tr("설명한 피크들의 반복 수 범위"),
            tr("설명한 피크들의 평균 질량 오차"),
            tr("Σ 가중치(오차가 작을수록 1에 가까움) × (최장 연속 구간이면 1, 아니면 0.5)"),
            tr("이 계열 후보들이 각 피크에서 받은 확률의 평균"),
        ])
        self._fam_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._fam_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._fam_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._fam_table.setAlternatingRowColors(True)
        self._fam_table.verticalHeader().setVisible(False)
        for c, w in enumerate([52, 330, 96, 84, 80, 118, 70, 84]):
            self._fam_table.setColumnWidth(c, w)
        fit_header(self._fam_table)
        self._fam_table.itemSelectionChanged.connect(self._on_family_selected)
        fb.addWidget(self._fam_table)
        self._tabs.addTab(fam_box, tr("조성 계열"))

        self._kmd = KmdPanel()
        self._kmd.peak_clicked.connect(self.select_peak)
        self._tabs.addTab(self._kmd, "KMD")
        self._tabs.setTabToolTip(0, tr("선택한 피크의 후보 조성 (확률 순)"))
        self._tabs.setTabToolTip(1, tr("연속 반복 수로 묶은 조성 계열 순위"))
        self._tabs.setTabToolTip(2, tr("Kendrick mass defect 플롯"))
        self._splitter.addWidget(self._tabs)

        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setStretchFactor(2, 3)
        root.addWidget(self._splitter)
        self._splitter.setSizes([0, 380, 420])
        self._refresh_table()

    # ------------------------------------------------------------------
    # 입력: 피크 목록 / 스펙트럼
    # ------------------------------------------------------------------

    def set_spectrum(self, spec: Spectrum | None, title: str = "") -> None:
        self._spectrum = spec
        self._spec_box.setVisible(spec is not None)
        self._plot.set_spectrum(spec)
        self._spec_title.setText(title)
        self._splitter.setSizes([340, 230, 320] if spec is not None else [0, 380, 420])

    def set_peaks(self, peaks: list[tuple[float, float | None, float | None, str]], replace: bool = True) -> None:
        """[(m/z, 강도, S/N, 메모)] 로 피크 목록을 설정/추가한다."""
        new = [PeakRow(mz=m, intensity=i, snr=s, note=n) for m, i, s, n in peaks]
        self._rows = new if replace else self._rows + new
        self._series = []
        self.clear_results()
        self.peaks_changed.emit()

    def load_peak_data(self, pd: PeakData) -> None:
        rows = []
        for i, mz in enumerate(pd.mz_values):
            rows.append(PeakRow(
                mz=mz,
                intensity=pd.intensities[i] if i < len(pd.intensities) else None,
                enabled=pd.enabled[i] if i < len(pd.enabled) else True,
                note=pd.notes[i] if i < len(pd.notes) else "",
            ))
        self._rows = rows
        self._series = []
        self.clear_results()

    def to_peak_data(self) -> PeakData:
        return PeakData(
            mz_values=[r.mz for r in self._rows],
            intensities=[r.intensity if r.intensity is not None else 0.0 for r in self._rows],
            enabled=[r.enabled for r in self._rows],
            notes=[r.note for r in self._rows],
        )

    def update_series(self, repeats: dict[str, float], tol: float, min_length: int = 4, max_gap: int = 1) -> list[PeakSeries]:
        """반복단위 간격 시리즈를 검출해 피크별 시리즈 정보를 갱신한다."""
        self._repeats = repeats
        for r in self._rows:
            r.series_ids = []
        if self._rows and repeats:
            order = np.argsort([r.mz for r in self._rows], kind="stable")
            mz = np.array([self._rows[i].mz for i in order])
            series = detect_series(mz, repeats, tol, min_length, max_gap)
            for s in series:
                s.peak_indices = sorted(int(order[i]) for i in s.peak_indices)
                for i in s.peak_indices:
                    self._rows[i].series_ids.append(s.series_id)
            self._series = series
        else:
            self._series = []
        self._refresh_table()
        return self._series

    def solve_targets(self) -> tuple[list[int], list[float]]:
        """솔버에 넣을 (행 인덱스, m/z) — 사용 체크 + (필터 시) 시리즈 피크만."""
        rows = [i for i, r in enumerate(self._rows)
                if r.enabled and r.mz > 0 and (not self._series_only.isChecked() or r.series_ids)]
        return rows, [self._rows[i].mz for i in rows]

    def peak_count(self) -> int:
        return len(self._rows)

    # ------------------------------------------------------------------
    # 결과
    # ------------------------------------------------------------------

    def set_results(self, rows: list[int], result_sets: list[RankedResultSet],
                    families: list[CompositionFamily]) -> None:
        for r in self._rows:
            r.result = None
        for i, rs in zip(rows, result_sets):
            self._rows[i].result = rs
        self._solved_rows = rows
        self._families = families
        self._family_by_id = {f.family_id: f for f in families}
        self._fill_family_table()
        self._refresh_table()
        # 후보가 있는 피크 중 가장 강한 피크를 선택 (강도 정보가 없으면 첫 피크)
        best = max(
            (i for i in rows if self._rows[i].result and self._rows[i].result.results),
            key=lambda i: self._rows[i].intensity or 0.0,
            default=rows[0] if rows else None,
        )
        if best is not None:
            self.select_peak(best)
        if families:
            self._tabs.setCurrentIndex(0)

    def add_detail_tab(self, widget: QWidget, title: str, tooltip: str = "") -> int:
        """상세 탭에 위젯을 추가한다 (예: 메시지 로그)."""
        idx = self._tabs.addTab(widget, title)
        if tooltip:
            self._tabs.setTabToolTip(idx, tooltip)
        return idx

    def families(self) -> list[CompositionFamily]:
        return list(self._families)

    def result_summary(self) -> dict:
        """결과 요약 띠용 숫자: 할당된 피크 수, 솔버 대상 수, 시리즈 수."""
        assigned = sum(1 for i in self._solved_rows if self._rows[i].result and self._rows[i].result.results)
        return {"assigned": assigned, "solved": len(self._solved_rows), "peaks": len(self._rows),
                "series": len(self._series)}

    def select_family(self, family_id: int) -> None:
        """조성 계열 탭으로 가서 그 계열을 고른다 (피크 강조)."""
        for r in range(self._fam_table.rowCount()):
            if self._fam_table.item(r, 0).data(Qt.UserRole) == family_id:
                self._tabs.setCurrentIndex(1)
                self._fam_table.selectRow(r)
                return

    def get_state(self) -> dict:
        """언어 전환 때 새 창으로 옮길 상태 (데이터 객체는 공유)."""
        return {
            "rows": self._rows, "series": self._series, "families": self._families,
            "solved_rows": self._solved_rows, "repeats": self._repeats, "spectrum": self._spectrum,
            "spec_title": self._spec_title.text(), "series_only": self._series_only.isChecked(),
            "selected": self._current_row(), "tab": self._tabs.currentIndex(),
            "splitter": self._splitter.sizes(), "view_range": self._plot.getPlotItem().getViewBox().viewRange(),
        }

    def set_state(self, st: dict) -> None:
        self.set_spectrum(st.get("spectrum"), st.get("spec_title", ""))
        self._rows = st.get("rows", [])
        self._series = st.get("series", [])
        self._repeats = st.get("repeats", {})
        self._solved_rows = st.get("solved_rows", [])
        self._families = st.get("families", [])
        self._family_by_id = {f.family_id: f for f in self._families}
        self._series_only.setChecked(bool(st.get("series_only")))
        self._fill_family_table()
        self._refresh_table()
        if st.get("splitter"):
            self._splitter.setSizes(st["splitter"])
        if st.get("spectrum") is not None and st.get("view_range"):
            (x0, x1), _ = st["view_range"]
            self._plot.setXRange(x0, x1, padding=0)
        if st.get("selected") is not None:
            self.select_peak(st["selected"])
        self._tabs.setCurrentIndex(int(st.get("tab", 0)))

    def clear_results(self) -> None:
        for r in self._rows:
            r.result = None
        self._families, self._family_by_id, self._solved_rows = [], {}, []
        self._fam_table.setRowCount(0)
        self._result_view.clear()
        self._set_highlight([], [])
        self._refresh_table()

    # ------------------------------------------------------------------
    # 선택 / 강조
    # ------------------------------------------------------------------

    def select_peak(self, row: int) -> None:
        if 0 <= row < self._table.rowCount():
            if self._table.isRowHidden(row):
                self._series_only.setChecked(False)
            self._table.selectRow(row)
            self._table.scrollToItem(self._table.item(row, C_MZ), QAbstractItemView.PositionAtCenter)

    def _current_row(self) -> int | None:
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _on_table_selection(self) -> None:
        row = self._current_row()
        self._plot.set_selected(row)
        if row is None or row >= len(self._rows):
            return
        r = self._rows[row]
        if r.result is None:
            self._result_view.clear()
            self._set_highlight([], [])
            return
        note = f" · {r.note}" if r.note else ""
        self._result_view.display_results(r.result, f"m/z {r.mz:.4f}{note}")
        if not r.result.results:
            self._set_highlight([], [])

    def _on_candidate_selected(self, res: SolverResult | None) -> None:
        fam = self._family_by_id.get(res.family_id) if res is not None and res.family_id else None
        self._highlight_family(fam)

    def _on_family_selected(self) -> None:
        sel = self._fam_table.selectionModel().selectedRows()
        if not sel:
            return
        fid = self._fam_table.item(sel[0].row(), 0).data(Qt.UserRole)
        self._highlight_family(self._family_by_id.get(fid))

    def _highlight_family(self, fam: CompositionFamily | None) -> None:
        if fam is None:
            self._set_highlight([], [])
            return
        rows = [self._solved_rows[p] for p, _n, _e, _c in fam.members]
        labels = [f"{fam.repeat_name}{n}" if len(fam.members) <= 40 else str(n) for _p, n, _e, _c in fam.members]
        self._set_highlight(rows, labels)

    def _set_highlight(self, rows: list[int], labels: list[str]) -> None:
        old = self._highlight_rows
        self._highlight_rows = set(rows)
        self._plot.set_family(rows, labels)
        self._paint_highlight(old | self._highlight_rows)

    def _paint_highlight(self, rows: set[int]) -> None:
        self._table.blockSignals(True)
        for r in rows:
            if r < self._table.rowCount():
                for c in range(self._table.columnCount()):
                    it = self._table.item(r, c)
                    if it is not None:
                        it.setBackground(QBrush(QColor(theme.FAMILY_HL_BG)) if r in self._highlight_rows else QBrush())
        self._table.blockSignals(False)

    # ------------------------------------------------------------------
    # 테이블 렌더링
    # ------------------------------------------------------------------

    def _series_color(self, row: PeakRow) -> str:
        return theme.series_color(row.series_ids[0] if row.series_ids else None)

    def _refresh_table(self) -> None:
        sel = self._current_row()
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._rows))
        editable = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        readonly = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        for i, r in enumerate(self._rows):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            use.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
            self._table.setItem(i, C_USE, use)

            def cell(col, text, flags=readonly, color=None):
                it = NumericTableWidgetItem(text) if col not in (C_BEST, C_NOTE, C_SERIES, C_ADDUCT) else QTableWidgetItem(text)
                it.setFlags(flags)
                if col not in (C_BEST, C_NOTE, C_SERIES, C_ADDUCT):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if color:
                    it.setForeground(QBrush(QColor(color)))
                self._table.setItem(i, col, it)

            in_spectrum = self._spectrum is not None
            cell(C_MZ, f"{r.mz:.4f}", readonly if in_spectrum else editable)
            cell(C_INT, f"{r.intensity:.4g}" if r.intensity is not None else "", readonly if in_spectrum else editable)
            cell(C_SNR, f"{r.snr:.1f}" if r.snr is not None else "")
            cell(C_SERIES, ",".join(f"S{s}" for s in r.series_ids), color=self._series_color(r))
            best = r.result.results[0] if r.result and r.result.results else None
            cell(C_NCAND, str(r.result.count()) if r.result else "")
            cell(C_BEST, best.composition.to_string() if best else ("—" if r.result else ""))
            cell(C_PROB, f"{best.probability * 100:.0f}%" if best and best.probability is not None else "")
            cell(C_ADDUCT, ion_text(best.adduct_label) if best else "")
            cell(C_FAM, str(best.family_support) if best and best.family_id else "")
            cell(C_NOTE, r.note, editable)
            if best and best.probability is not None and best.probability >= 0.8:
                self._table.item(i, C_PROB).setForeground(QBrush(QColor(theme.GOOD)))
        self._table.blockSignals(False)
        self._apply_filter()
        self._update_plot_peaks()
        self._paint_highlight(self._highlight_rows)
        if sel is not None and sel < len(self._rows):
            self._table.selectRow(sel)

    def _apply_filter(self) -> None:
        only = self._series_only.isChecked()
        for i, r in enumerate(self._rows):
            self._table.setRowHidden(i, only and not r.series_ids)
        n_use = len(self.solve_targets()[0])
        n_series = sum(1 for r in self._rows if r.series_ids)
        txt = tr("피크 {n}개 · 솔버 대상 {m}개", n=len(self._rows), m=n_use)
        if self._series:
            txt += " · " + tr("시리즈 {s}개 ({p}개 피크)", s=len(self._series), p=n_series)
        self._peak_count.setText(txt)

    def _update_plot_peaks(self) -> None:
        mz = np.array([r.mz for r in self._rows], dtype=float)
        if self._spectrum is not None and self._spectrum.size:
            y = np.array([r.intensity if r.intensity is not None else
                          float(np.interp(r.mz, self._spectrum.mz, self._spectrum.intensity))
                          for r in self._rows], dtype=float)
        else:
            y = np.array([r.intensity or 0.0 for r in self._rows], dtype=float)
        colors = [self._series_color(r) for r in self._rows]
        self._plot.set_peaks(mz, y, colors)
        self._kmd.set_data(self._repeats, mz, colors)

    def _fill_family_table(self) -> None:
        self._fam_table.setRowCount(0)
        for f in self._families[:500]:
            row = self._fam_table.rowCount()
            self._fam_table.insertRow(row)
            lo, hi = f.n_range
            vals = [str(f.family_id), ion_text(f.label()), str(f.support), str(f.run_length), f"{lo}–{hi}",
                    f"{f.mean_abs_error:.4f}", f"{f.score:.1f}", f"{f.mean_probability * 100:.0f}%"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v) if c == 1 else NumericTableWidgetItem(v)
                if c != 1:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._fam_table.setItem(row, c, it)
            self._fam_table.item(row, 0).setData(Qt.UserRole, f.family_id)
        self._tabs.setTabText(1, f"{tr('조성 계열')} ({len(self._families)})")

    # ------------------------------------------------------------------
    # 편집 (질량 목록 모드)
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        i, c = item.row(), item.column()
        if i >= len(self._rows):
            return
        r = self._rows[i]
        if c == C_USE:
            r.enabled = item.checkState() == Qt.Checked
            self._apply_filter()
            return
        if c == C_NOTE:
            r.note = item.text()
            return
        try:
            val = float(item.text()) if item.text().strip() else None
        except ValueError:
            val = None
        if c == C_MZ and val and val > 0 and abs(val - r.mz) > 1e-9:
            r.mz, r.result = val, None
            self._series = []
            for row in self._rows:
                row.series_ids = []
            self.peaks_changed.emit()
            self._refresh_table()
        elif c == C_INT:
            r.intensity = val

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        from qtpy.QtGui import QKeySequence
        if ev.matches(QKeySequence.Paste):
            self._paste()
            return
        super().keyPressEvent(ev)

    def _paste(self) -> None:
        from mpcs.infrastructure.file_io import parse_peak_rows, split_text_rows
        peaks = parse_peak_rows(split_text_rows(QApplication.clipboard().text()))
        if not peaks:
            QMessageBox.information(self, tr("붙여넣기"), tr("클립보드에서 m/z 숫자를 찾을 수 없습니다."))
            return
        self._append_manual(peaks)

    def _import_file(self) -> None:
        from mpcs.infrastructure.file_io import FileImportError, read_peak_table
        path, _ = QFileDialog.getOpenFileName(
            self, tr("피크 표 가져오기"), "", tr("표 파일 (*.xlsx *.xls *.csv *.txt);;모든 파일 (*.*)"))
        if not path:
            return
        try:
            self._append_manual(read_peak_table(path))
        except FileImportError as exc:
            QMessageBox.critical(self, tr("가져오기 실패"), str(exc))

    def _append_manual(self, peaks: list[tuple[float, float | None, str]]) -> None:
        replace = False
        if self._rows:
            box = QMessageBox(self)
            box.setWindowTitle(tr("피크 추가"))
            box.setText(tr("{n}개 피크를 가져왔습니다. 기존 목록을 어떻게 할까요?", n=len(peaks)))
            add = box.addButton(tr("뒤에 추가"), QMessageBox.AcceptRole)
            rep = box.addButton(tr("교체"), QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec_()
            if box.clickedButton() not in (add, rep):
                return
            replace = box.clickedButton() is rep
        self.set_peaks([(m, i, None, n) for m, i, n in peaks], replace=replace or not self._rows)

    def _add_row(self) -> None:
        self._rows.append(PeakRow(mz=0.0))
        self._refresh_table()
        row = len(self._rows) - 1
        self._table.selectRow(row)
        self._table.editItem(self._table.item(row, C_MZ))

    def _delete_selected(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self._rows[r]
        if rows:
            self._series = []
            self.clear_results()
            self.peaks_changed.emit()

    def _clear_rows(self) -> None:
        if self._rows and QMessageBox.question(self, tr("모두 지우기"), tr("피크 목록을 모두 지울까요?")) == QMessageBox.Yes:
            self._rows = []
            self._series = []
            self.clear_results()
            self.peaks_changed.emit()

    # ------------------------------------------------------------------
    # 내보내기
    # ------------------------------------------------------------------

    def export_all(self) -> None:
        if not any(r.result for r in self._rows):
            QMessageBox.information(self, tr("내보내기"), tr("솔버를 먼저 실행하십시오."))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("전체 결과 내보내기"), "", "Excel Files (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            self.write_excel(path)
            QMessageBox.information(self, tr("내보내기 완료"), path)
        except Exception as exc:
            QMessageBox.critical(self, tr("내보내기 오류"), str(exc))

    def write_excel(self, path: str) -> None:
        """시트: 피크 요약 / 전체 후보 / 조성 계열."""
        import pandas as pd

        summary, cands = [], []
        for i, r in enumerate(self._rows):
            best = r.result.results[0] if r.result and r.result.results else None
            summary.append({
                "#": i + 1, "m/z": r.mz, "intensity": r.intensity, "S/N": r.snr,
                "series": ",".join(f"S{s}" for s in r.series_ids), "candidates": r.result.count() if r.result else None,
                "best composition": best.composition.to_string() if best else None,
                "probability": best.probability if best else None,
                "adduct": best.adduct_label if best else None,
                "error (Da)": best.error_da if best else None,
                "family peaks": best.family_support if best and best.family_id else None,
                "note": r.note,
            })
            if r.result:
                for rank, c in enumerate(r.result.results, start=1):
                    row = {"peak #": i + 1, "observed m/z": r.mz, "rank": rank, "probability": c.probability,
                           "formula": c.formula, "calculated m/z": c.calculated_mass, "error (Da)": c.error_da,
                           "adduct": c.adduct_label, "isotope offset": c.isotope_offset,
                           "family": c.family_id, "family peaks": c.family_support}
                    row.update({f"n_{k}": v for k, v in c.composition.counts})
                    cands.append(row)
        fams = [{"rank": f.family_id, "family": f.label(), "repeat unit": f.repeat_name,
                 "fixed": " ".join(f"{k}{v}" for k, v in f.fixed if v), "adduct": f.adduct_label,
                 "isotope offset": f.isotope_offset, "peaks explained": f.support, "longest run": f.run_length,
                 "n min": f.n_range[0], "n max": f.n_range[1], "mean |error| (Da)": f.mean_abs_error,
                 "score": f.score, "mean probability": f.mean_probability} for f in self._families]
        with pd.ExcelWriter(path) as xw:
            pd.DataFrame(summary).to_excel(xw, sheet_name="peaks", index=False)
            pd.DataFrame(cands).to_excel(xw, sheet_name="candidates", index=False)
            pd.DataFrame(fams).to_excel(xw, sheet_name="families", index=False)
