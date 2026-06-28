"""
MPCS — GUI Dialog: Isotope Pattern Viewer
동위원소 패턴 시뮬레이션 다이얼로그

molmass 패키지를 이용해 주어진 분자식의 동위원소 스펙트럼을 계산하고
ChemDraw Analysis 스타일의 Stem Plot(막대형 m/z 스펙트럼)으로 시각화한다.

규칙:
    - 최대 intensity 기준 10% 미만 피크 제외
    - 최대 10개 피크만 표시
    - 가장 높은 intensity = 100% 기준으로 정규화
"""

from __future__ import annotations

from qtpy.QtCore import Qt, QRectF, QPointF
from qtpy.QtGui import (
    QColor, QFont, QPainter, QPen, QFontMetrics,
)
from qtpy.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from mpcs.core.formatting import format_formula_html, format_adduct_html
from mpcs.core.i18n import tr


# ---------------------------------------------------------------------------
# 스펙트럼 계산
# ---------------------------------------------------------------------------

def _compute_isotope_peaks(
    formula: str,
    min_intensity_pct: float = 10.0,
    max_peaks: int = 10,
) -> list[tuple[float, float]]:
    """
    분자식으로부터 동위원소 m/z–intensity 쌍 목록을 반환한다.

    Args:
        formula:           분자식 문자열 (예: "C100H200Na")
        min_intensity_pct: 최소 상대 intensity % (이 미만 제외)
        max_peaks:         최대 피크 개수

    Returns:
        [(mz, relative_intensity_pct), ...] 오름차순 정렬
        상대 intensity는 최대 피크 = 100% 기준.
    """
    try:
        import molmass
        spec = molmass.Formula(formula).spectrum()
    except Exception as exc:
        raise ValueError(f"스펙트럼 계산 실패: {exc}") from exc

    entries = list(spec.values())
    if not entries:
        return []

    # 최대 intensity 기준으로 정규화
    max_intensity = max(e.intensity for e in entries)
    if max_intensity <= 0:
        return []

    peaks = [
        (e.mz, e.intensity / max_intensity * 100.0)
        for e in entries
        if e.intensity / max_intensity * 100.0 >= min_intensity_pct
    ]

    # 상대 intensity 내림차순으로 잘라 상위 max_peaks만
    peaks.sort(key=lambda p: p[1], reverse=True)
    peaks = peaks[:max_peaks]

    # m/z 오름차순으로 재정렬
    peaks.sort(key=lambda p: p[0])
    return peaks


# ---------------------------------------------------------------------------
# 커스텀 스펙트럼 캔버스 (Stem Plot)
# ---------------------------------------------------------------------------

class _SpectrumCanvas(QWidget):
    """QPainter로 동위원소 Stem Plot을 렌더링하는 위젯."""

    MARGIN_LEFT   = 70
    MARGIN_RIGHT  = 30
    MARGIN_TOP    = 40
    MARGIN_BOTTOM = 55

    # 색상 팔레트 (모던 라이트 테마 고대비)
    COLOR_BG      = QColor("#ffffff")
    COLOR_AXIS    = QColor("#495057")
    COLOR_STEM    = QColor("#339af0")
    COLOR_PEAK    = QColor("#f03e3e")
    COLOR_LABEL   = QColor("#212529")
    COLOR_GRID    = QColor("#e9ecef")
    COLOR_100     = QColor("#e03131")   # 100% 피크 강조

    def __init__(self, peaks: list[tuple[float, float]], formula: str, parent=None):
        super().__init__(parent)
        self._peaks = peaks
        self._formula = formula
        self.setMinimumSize(600, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.COLOR_BG)
        self.setPalette(palette)

    def paintEvent(self, event):  # noqa: N802
        if not self._peaks:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        plot_w = w - self.MARGIN_LEFT - self.MARGIN_RIGHT
        plot_h = h - self.MARGIN_TOP - self.MARGIN_BOTTOM

        mz_values  = [p[0] for p in self._peaks]
        int_values = [p[1] for p in self._peaks]

        mz_min = min(mz_values)
        mz_max = max(mz_values)
        mz_range = mz_max - mz_min if mz_max > mz_min else 1.0
        # x 패딩: 양 끝 피크가 잘리지 않도록
        x_pad = max(mz_range * 0.12, 0.5)
        x_min = mz_min - x_pad
        x_max = mz_max + x_pad

        def _x(mz: float) -> float:
            return self.MARGIN_LEFT + (mz - x_min) / (x_max - x_min) * plot_w

        def _y(intensity_pct: float) -> float:
            return self.MARGIN_TOP + plot_h - (intensity_pct / 100.0) * plot_h

        # ─── 배경 그리드 ───────────────────────────────────────────────
        grid_pen = QPen(self.COLOR_GRID, 1, Qt.DotLine)
        painter.setPen(grid_pen)
        for pct in (20, 40, 60, 80, 100):
            gy = _y(pct)
            painter.drawLine(
                QPointF(self.MARGIN_LEFT, gy),
                QPointF(w - self.MARGIN_RIGHT, gy),
            )

        # ─── 축 ────────────────────────────────────────────────────────
        axis_pen = QPen(self.COLOR_AXIS, 1.5)
        painter.setPen(axis_pen)
        # x축
        y_base = _y(0)
        painter.drawLine(
            QPointF(self.MARGIN_LEFT, y_base),
            QPointF(w - self.MARGIN_RIGHT, y_base),
        )
        # y축
        painter.drawLine(
            QPointF(self.MARGIN_LEFT, self.MARGIN_TOP),
            QPointF(self.MARGIN_LEFT, y_base),
        )

        # ─── y축 레이블 ────────────────────────────────────────────────
        axis_font = QFont("Segoe UI", 10)
        painter.setFont(axis_font)
        painter.setPen(QPen(self.COLOR_LABEL))
        for pct in (0, 20, 40, 60, 80, 100):
            gy = _y(pct)
            txt = f"{pct}%"
            fm = QFontMetrics(axis_font)
            tw = fm.horizontalAdvance(txt)
            painter.drawText(
                QPointF(self.MARGIN_LEFT - tw - 6, gy + fm.ascent() / 2),
                txt,
            )

        # ─── 피크 Stem ─────────────────────────────────────────────────
        stem_pen = QPen(self.COLOR_STEM, 2.5)
        peak100_pen = QPen(self.COLOR_100, 2.5)

        label_font = QFont("Segoe UI", 10)
        painter.setFont(label_font)
        fm_lbl = QFontMetrics(label_font)

        peak_dot_radius = 3.5

        for mz, intensity in self._peaks:
            is_100 = abs(intensity - 100.0) < 0.5
            pen = peak100_pen if is_100 else stem_pen
            painter.setPen(pen)

            px = _x(mz)
            py = _y(intensity)
            yb = _y(0)

            # 수직 막대
            painter.drawLine(QPointF(px, yb), QPointF(px, py))

            # 상단 원점
            dot_color = self.COLOR_100 if is_100 else self.COLOR_STEM
            painter.setBrush(dot_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(px, py), peak_dot_radius, peak_dot_radius)
            painter.setBrush(Qt.NoBrush)

            # m/z 레이블 (소수점 4자리)
            mz_txt = f"{mz:.4f}"
            int_txt = f"{intensity:.1f}%"
            mz_w = fm_lbl.horizontalAdvance(mz_txt)
            painter.setPen(QPen(self.COLOR_LABEL))
            # m/z 값은 피크 상단 위
            painter.drawText(
                QPointF(px - mz_w / 2, py - peak_dot_radius - 14),
                mz_txt,
            )
            # intensity %는 m/z 바로 위
            int_w = fm_lbl.horizontalAdvance(int_txt)
            painter.drawText(
                QPointF(px - int_w / 2, py - peak_dot_radius - 3),
                int_txt,
            )

        # ─── x축 레이블 (m/z) ──────────────────────────────────────────
        painter.setFont(axis_font)
        painter.setPen(QPen(self.COLOR_LABEL))
        for mz, _ in self._peaks:
            px = _x(mz)
            txt = f"{int(mz)}"
            tw = fm_lbl.horizontalAdvance(txt)
            painter.drawText(
                QPointF(px - tw / 2, y_base + 18),
                txt,
            )

        # ─── 축 제목 ───────────────────────────────────────────────────
        title_font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QPen(self.COLOR_LABEL))
        # x축 제목
        x_title = "m/z"
        tw = QFontMetrics(title_font).horizontalAdvance(x_title)
        painter.drawText(
            QPointF(w / 2 - tw / 2, h - 8),
            x_title,
        )
        # y축 제목 (회전)
        painter.save()
        painter.translate(14, h / 2)
        painter.rotate(-90)
        y_title = "Relative Intensity (%)"
        tw = QFontMetrics(title_font).horizontalAdvance(y_title)
        painter.drawText(QPointF(-tw / 2, 0), y_title)
        painter.restore()

        # ─── 분자식 표시 ───────────────────────────────────────────────
        # QPainter는 단순 문자열을 그리므로, 캔버스에서는 HTML이 아닌 기본 문자열을 출력하거나
        # 또는 HTML 렌더링이 필요하다면 QTextDocument를 써야 함.
        # 여기서는 단순히 문자열만 표시 (캔버스 렌더링 부분). 
        formula_font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(formula_font)
        painter.setPen(QPen(self.COLOR_LABEL))
        formula_txt = f"{tr('분자식 (Formula)')}: {self._formula}"
        painter.drawText(QPointF(self.MARGIN_LEFT + 6, self.MARGIN_TOP - 12), formula_txt)

# ---------------------------------------------------------------------------
# 다이얼로그
# ---------------------------------------------------------------------------

class IsotopePatternDialog(QDialog):
    """
    동위원소 패턴 시뮬레이션 다이얼로그.

    주어진 분자식에 대해 molmass를 이용해 동위원소 분포를 계산하고
    ChemDraw Analysis 형태의 Stem Plot으로 시각화한다.
    """

    def __init__(self, formula: str, adduct_label: str = "", parent=None):
        super().__init__(parent)
        self._formula = formula
        self._adduct_label = adduct_label
        self.setWindowTitle(f"동위원소 패턴 — {formula}")
        self.setMinimumSize(720, 480)
        self.resize(820, 520)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── 정보 헤더 ──────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        fmt_formula = format_formula_html(self._formula)
        formula_label = QLabel(f"<b>분자식:</b> {fmt_formula}")
        formula_label.setStyleSheet("font-size: 11pt; color: #212529;")
        header_layout.addWidget(formula_label)

        if self._adduct_label:
            fmt_adduct = format_adduct_html(self._adduct_label)
            adduct_lbl = QLabel(f"<b>{tr('어덕트')}:</b> {fmt_adduct}")
            adduct_lbl.setStyleSheet("font-size: 11pt; color: #339af0;")
            header_layout.addWidget(adduct_lbl)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # ── 스펙트럼 계산 ──────────────────────────────────────────────
        try:
            peaks = _compute_isotope_peaks(self._formula)
        except ValueError as exc:
            err_label = QLabel(f"<span style='color:#f38ba8'>오류: {exc}</span>")
            layout.addWidget(err_label)
            peaks = []

        if peaks:
            # ── 피크 테이블 (요약) ─────────────────────────────────────
            from qtpy.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
            table = QTableWidget(len(peaks), 2)
            table.setHorizontalHeaderLabels(["m/z", "상대 Intensity (%)"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setAlternatingRowColors(True)
            table.setMaximumHeight(160)
            # Remove hardcoded dark theme CSS to inherit modern light theme
            table.setStyleSheet("")
            for row, (mz, intensity) in enumerate(peaks):
                mz_item = QTableWidgetItem(f"{mz:.4f}")
                mz_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                int_item = QTableWidgetItem(f"{intensity:.2f}%")
                int_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if abs(intensity - 100.0) < 0.5:
                    mz_item.setForeground(QColor("#e03131"))
                    int_item.setForeground(QColor("#e03131"))
                    font = mz_item.font()
                    font.setBold(True)
                    mz_item.setFont(font)
                    int_item.setFont(font)
                table.setItem(row, 0, mz_item)
                table.setItem(row, 1, int_item)

            layout.addWidget(table)

            # ── 스펙트럼 그래프 ────────────────────────────────────────
            canvas = _SpectrumCanvas(peaks, self._formula)
            layout.addWidget(canvas)
        else:
            layout.addWidget(QLabel("표시할 피크가 없습니다."))

        # ── 닫기 버튼 ─────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
