"""
MPCS — MALDI Polymer Composition Solver
GUI Layer: SideRail (접힌 입력 패널 자리의 좁은 아이콘 막대) · PanelSplitter

입력 패널(서열 / 데이터·설정 탭)을 접으면 그 자리에 폭 RAIL_WIDTH(40 px)의 막대가 남는다.
    맨 위   펼치기 버튼 (panel-left-open)          → expand_requested
    그 아래 탭마다 아이콘 버튼 (예: dna, sliders)   → tab_requested(index)  (펼치고 그 탭으로)

PanelSplitter: 손잡이를 두 번 누르면 handle_double_clicked(index)를 보낸다 (패널 접기/펼치기).
"""

from __future__ import annotations

from qtpy.QtCore import QSize, Qt, Signal
from qtpy.QtWidgets import QSplitter, QSplitterHandle, QToolButton, QVBoxLayout, QWidget

from mpcs.core.i18n import tr
from mpcs.gui import theme
from mpcs.gui.icons import icon

RAIL_WIDTH = 40


class SideRail(QWidget):
    """접힌 입력 패널의 아이콘 막대."""

    expand_requested = Signal()
    tab_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sideRail")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_WIDTH)
        t = theme
        self.setStyleSheet(f"""
QWidget#sideRail {{ background: {t.SURFACE}; border-right: 1px solid {t.BORDER}; }}
QWidget#sideRail QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: {t.RADIUS}px; padding: 5px;
}}
QWidget#sideRail QToolButton:hover {{ background: {t.ACCENT_SOFT}; }}
QWidget#sideRail QToolButton:checked {{ background: {t.ACCENT_SOFT}; border-color: {t.BORDER}; }}
""")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(4)
        self._lay = lay
        self.expand_btn = self._button("panel-left-open", tr("입력 패널 펼치기") + " (Ctrl+B)")
        self.expand_btn.clicked.connect(self.expand_requested.emit)
        lay.addWidget(self.expand_btn, 0, Qt.AlignHCenter)
        sep = QWidget(self)
        sep.setFixedHeight(1)
        sep.setAttribute(Qt.WA_StyledBackground, True)
        sep.setStyleSheet(f"background: {t.BORDER};")
        lay.addWidget(sep)
        self.tab_buttons: list[QToolButton] = []
        lay.addStretch(1)

    def _button(self, icon_name: str, tooltip: str, checkable: bool = False) -> QToolButton:
        b = QToolButton(self)
        b.setIcon(icon(icon_name, theme.TEXT_2, 20, checked_color=theme.ACCENT))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(32, 32)
        b.setToolTip(tooltip)
        b.setCheckable(checkable)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def add_tab_button(self, icon_name: str, tooltip: str) -> QToolButton:
        """탭 하나에 대응하는 버튼 (추가 순서 = 탭 index)."""
        index = len(self.tab_buttons)
        b = self._button(icon_name, tooltip, checkable=True)
        b.clicked.connect(lambda _c=False, i=index: self._on_tab(i))
        self._lay.insertWidget(self._lay.count() - 1, b, 0, Qt.AlignHCenter)
        self.tab_buttons.append(b)
        return b

    def _on_tab(self, index: int) -> None:
        self.set_current(index)
        self.tab_requested.emit(index)

    def set_current(self, index: int) -> None:
        for i, b in enumerate(self.tab_buttons):
            b.setChecked(i == index)


class _Handle(QSplitterHandle):
    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        sp = self.splitter()
        if isinstance(sp, PanelSplitter):
            sp.handle_double_clicked.emit(sp.indexOf(self))
        ev.accept()


class PanelSplitter(QSplitter):
    """손잡이 두 번 누름을 알리는 QSplitter."""

    handle_double_clicked = Signal(int)

    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return _Handle(self.orientation(), self)


__all__ = ["PanelSplitter", "RAIL_WIDTH", "SideRail"]
