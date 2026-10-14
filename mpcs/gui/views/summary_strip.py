"""
MPCS — MALDI Polymer Composition Solver
GUI View: ResultSummaryStrip (결과 요약 띠)

결과 영역 맨 위 한 줄:
    [최상위 조성 계열] [확률] [피크 할당] [2위 계열]
계열 칸을 누르면 family_clicked(family_id) — 메인 윈도우가 조성 계열 탭에서 그 계열을 고른다.
결과가 없으면 안내 문구만 보인다.
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from mpcs.core.formatting import ion_text
from mpcs.core.i18n import tr
from mpcs.gui import theme
from mpcs.services.series_analysis import CompositionFamily


class _Segment(QFrame):
    """캡션 + 큰 값 + 보조 줄. 누르면 clicked."""

    clicked = Signal()

    def __init__(self, caption: str, tooltip: str, clickable: bool = False) -> None:
        super().__init__()
        self.setObjectName("summarySeg")
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        self.caption = QLabel(caption)
        self.caption.setObjectName("caption")
        self.value = QLabel("—")
        self.value.setTextFormat(Qt.PlainText)
        self.sub = QLabel("")
        self.sub.setObjectName("caption")
        for w in (self.caption, self.value, self.sub):
            lay.addWidget(w)

    def set(self, value: str, sub: str = "", color: str = theme.TEXT) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color}; font-size: {theme.FS_HERO - 4}px; font-weight: 600;")
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if self._clickable and ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class ResultSummaryStrip(QFrame):
    """솔버 결과 요약 띠."""

    family_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryStrip")
        self.setAttribute(Qt.WA_StyledBackground, True)
        t = theme
        self.setStyleSheet(f"""
QFrame#summaryStrip {{ background: {t.SURFACE}; border-bottom: 1px solid {t.BORDER}; }}
QFrame#summarySeg {{ background: transparent; border-radius: {t.RADIUS}px; }}
QFrame#summarySeg:hover {{ background: {t.ACCENT_TINT_2}; }}
""")
        self._stack = QStackedLayout(self)

        empty = QWidget()
        el = QHBoxLayout(empty)
        el.setContentsMargins(14, 10, 14, 10)
        msg = QLabel(tr("솔버를 실행하면 가장 가능성 높은 조성 계열이 여기에 표시됩니다."))
        msg.setObjectName("caption")
        el.addWidget(msg)
        el.addStretch()
        self._stack.addWidget(empty)

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.setSpacing(8)
        self.top = _Segment(tr("최상위 조성 계열"), tr(
            "가장 점수가 높은 조성 계열: 반복단위 n 범위 · 고정 조성 · 어덕트. 누르면 조성 계열 탭에서 강조합니다."), True)
        self.prob = _Segment(tr("확률"), tr(
            "최상위 계열 후보들이 각 피크에서 받은 확률의 평균. 비슷한 질량의 다른 계열이 있으면 낮아집니다."))
        self.assign = _Segment(tr("피크 할당"), tr("후보가 하나 이상 있는 피크 수 / 솔버에 넣은 피크 수"))
        self.second = _Segment(tr("2위 계열"), tr("두 번째로 점수가 높은 조성 계열. 누르면 강조합니다."), True)
        for seg in (self.top, self.prob, self.assign, self.second):
            bl.addWidget(seg)
        bl.addStretch()
        self._stack.addWidget(body)
        self._families: list[CompositionFamily] = []
        self.top.clicked.connect(lambda: self._emit(0))
        self.second.clicked.connect(lambda: self._emit(1))
        self.clear()

    def _emit(self, rank: int) -> None:
        if rank < len(self._families):
            self.family_clicked.emit(self._families[rank].family_id)

    def clear(self) -> None:
        self._families = []
        self._stack.setCurrentIndex(0)

    def set_result(self, families: list[CompositionFamily], summary: dict) -> None:
        """families: 점수순 조성 계열, summary: AnalysisView.result_summary()."""
        self._families = families
        self._stack.setCurrentIndex(1)
        if families:
            f = families[0]
            self.top.set(ion_text(f.label()), tr("설명 피크 {n} · 연속 {r} · 평균 오차 {e:.4f} Da",
                                                 n=f.support, r=f.run_length, e=f.mean_abs_error), theme.GOOD)
            p = f.mean_probability
            color = theme.GOOD if p >= 0.8 else (theme.WARN if p >= 0.5 else theme.TEXT_2)
            self.prob.set(f"{p * 100:.0f}%", "", color)
        else:
            self.top.set(tr("계열 없음"), tr("연속된 피크를 설명하는 조성 계열을 찾지 못했습니다."), theme.TEXT_2)
            self.prob.set("—")
        self.assign.set(f"{summary.get('assigned', 0)} / {summary.get('solved', 0)}",
                        tr("시리즈 {s}개", s=summary.get("series", 0)))
        if len(families) > 1:
            g = families[1]
            self.second.set(ion_text(g.label()), tr("설명 피크 {n}", n=g.support), theme.TEXT_2)
            self.second.setVisible(True)
        else:
            self.second.setVisible(False)


__all__ = ["ResultSummaryStrip"]
