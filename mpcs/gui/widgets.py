"""
MPCS — MALDI Polymer Composition Solver
GUI Layer: 공통 작은 위젯 헬퍼 (PepLCMS common.py에서 복사해 MPCS용으로 독립 관리)

QSS 역할 이름(objectName)을 붙인 라벨·구분선. 색은 theme.build_qss가 역할별로 정한다.
"""

from __future__ import annotations

from qtpy.QtWidgets import QFrame, QHeaderView, QLabel, QTableWidget, QWidget

from mpcs.gui import theme


def role_label(text: str, role: str, parent: QWidget | None = None) -> QLabel:
    """objectName=role인 QLabel (role: dialogTitle, panelTitle, sectionTitle, caption, keyValue, emptyState,
    legendItem, errorText, warnText, goodText — theme.build_qss 참조)."""
    lb = QLabel(text, parent)
    lb.setObjectName(role)
    return lb


def caption(text: str, wrap: bool = True, parent: QWidget | None = None) -> QLabel:
    """흐린 12 px 설명 글."""
    lb = role_label(text, "caption", parent)
    lb.setWordWrap(wrap)
    return lb


def set_role(label: QLabel, role: str) -> None:
    """라벨의 역할(objectName)을 바꾸고 스타일을 다시 적용한다 (예: caption ↔ errorText)."""
    if label.objectName() == role:
        return
    label.setObjectName(role)
    st = label.style()
    st.unpolish(label)
    st.polish(label)


def hline(parent: QWidget | None = None) -> QFrame:
    """가는 가로 구분선 (QFrame#rule, 1 px BORDER)."""
    f = QFrame(parent)
    f.setObjectName("rule")
    f.setFrameShape(QFrame.NoFrame)
    f.setFixedHeight(1)
    return f


def color_span(text: str, color: str, bold: bool = False) -> str:
    """rich text 조각: 토큰 색 글자 (뷰 코드에 hex를 쓰지 않도록)."""
    w = "; font-weight:600" if bold else ""
    return f"<span style='color:{color}{w}'>{text}</span>"


def set_header_tooltips(table: QTableWidget, tips: list[str]) -> None:
    """표 머리 칸마다 설명 툴팁을 단다 (열 수보다 짧으면 앞쪽만)."""
    for c, tip in enumerate(tips):
        item = table.horizontalHeaderItem(c)
        if item is not None and tip:
            item.setToolTip(tip)


def fit_header(table: QTableWidget) -> None:
    """머리 글자가 잘리지 않을 최소 폭을 보장한다 (언어에 따라 글자 길이가 다름)."""
    hh: QHeaderView = table.horizontalHeader()
    fm = hh.fontMetrics()
    for c in range(table.columnCount()):
        item = table.horizontalHeaderItem(c)
        if item is None or hh.isSectionHidden(c):
            continue
        need = fm.horizontalAdvance(item.text()) + theme.CELL_PAD + theme.HEADER_PAD + 12
        if hh.sectionSize(c) < need:
            hh.resizeSection(c, need)


__all__ = ["caption", "color_span", "fit_header", "hline", "role_label", "set_header_tooltips", "set_role"]
