"""
MPCS — MALDI Polymer Composition Solver
GUI Layer: CommandBar (메뉴 + 도구 모음을 합친 한 줄 명령 막대)

    [파일 분석 도구 도움말] │ [입력 패널] [스펙트럼 열기] [폴더 열기] [프로젝트 열기] [저장] │
    [▶ 분석 실행 (주 버튼)] [중단] │ [내보내기 ▾]  ……  [KO ▾]

- 메뉴 버튼은 메인 윈도우의 QMenu 객체를 그대로 쓴다 (InstantPopup). Alt+F/A/T/H 로 연다.
- 명령 버튼은 QAction을 따라간다 (활성/체크 상태 동기화, 클릭 → action.trigger()).
  버튼 글자는 짧은 이름을 따로 주고, 툴팁에 긴 설명 + 단축키를 넣는다.
- 창이 좁으면(COMPACT_WIDTH 미만) 아이콘만 표시한다 (주 버튼은 글자 유지).
- 색은 theme 토큰만 쓴다. 막대 자체의 모양은 이 모듈의 QSS(build_bar_qss)로 정한다.
"""

from __future__ import annotations

from qtpy.QtCore import QSize, Qt, Signal
from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import (
    QAction,
    QActionGroup,
    QMenu,
    QShortcut,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from mpcs.core.i18n import tr
from mpcs.gui import theme
from mpcs.gui.icons import icon

_GAP = " "
"""아이콘과 글자 사이 간격 (QToolButton 기본 간격이 좁다)."""

LANGUAGES: tuple[tuple[str, str, str], ...] = (("ko", "KO", "한국어"), ("en", "EN", "English"))
"""(코드, 버튼 표시, 메뉴 표시) — 언어 이름은 번역하지 않는다 (각 언어 고유 이름)."""


def build_bar_qss() -> str:
    """명령 막대·옆 막대 공용 QSS (theme 토큰)."""
    t = theme
    return f"""
QToolBar#commandBar {{
    background: {t.SURFACE}; border: none; border-bottom: 1px solid {t.BORDER};
    padding: 3px {t.SP_2}px; spacing: 2px;
}}
QToolBar#commandBar::separator {{ width: 1px; background: {t.BORDER}; margin: 6px {t.SP_1 + 2}px; }}
QToolBar#commandBar QToolButton {{
    color: {t.TEXT}; background: transparent; border: 1px solid transparent;
    border-radius: {t.RADIUS}px; padding: 4px 8px; font-size: {t.FS_BODY}px;
}}
QToolBar#commandBar QToolButton:hover {{ background: {t.ACCENT_SOFT}; color: {t.ACCENT_HOVER}; }}
QToolBar#commandBar QToolButton:pressed,
QToolBar#commandBar QToolButton:checked {{ background: {t.ACCENT_SOFT}; border-color: {t.BORDER}; }}
QToolBar#commandBar QToolButton:disabled {{ color: {t.REJECTED}; background: transparent; }}
QToolBar#commandBar QToolButton::menu-indicator {{ image: none; width: 0px; }}
QToolBar#commandBar QToolButton[role="menu"] {{ padding: 4px 10px; color: {t.TEXT_2}; }}
QToolBar#commandBar QToolButton[role="menu"]:hover {{ color: {t.ACCENT_HOVER}; }}
QToolBar#commandBar QToolButton[role="primary"] {{
    background: {t.ACCENT}; color: {t.SURFACE}; border-color: {t.ACCENT};
    font-weight: 600; padding: 4px 14px;
}}
QToolBar#commandBar QToolButton[role="primary"]:hover {{ background: {t.ACCENT_HOVER}; color: {t.SURFACE}; }}
QToolBar#commandBar QToolButton[role="primary"]:disabled {{
    background: {t.BORDER}; border-color: {t.BORDER}; color: {t.TEXT_3};
}}
"""


class ActionButton(QToolButton):
    """QAction을 따라가는 명령 버튼 (글자·아이콘은 버튼이 따로 가진다)."""

    def __init__(self, action: QAction, text: str, icon_name: str | None, *, primary: bool = False,
                 keep_text: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self.full_text = text
        self.icon_name = icon_name
        self.primary = primary
        self.keep_text = keep_text or primary
        self.setProperty("role", "primary" if primary else "action")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(True)
        self.setText(_GAP + text if icon_name else text)
        if icon_name:
            if primary:
                self.setIcon(icon(icon_name, theme.SURFACE, 16, active_color=theme.SURFACE,
                                  disabled_color=theme.TEXT_3))
            else:
                self.setIcon(icon(icon_name, theme.TEXT_2, 18, checked_color=theme.ACCENT))
        self.setCheckable(action.isCheckable())
        self.clicked.connect(self._on_clicked)
        action.changed.connect(self.sync)
        if action.isCheckable():
            action.toggled.connect(lambda _on: self.sync())
        self.sync()
        self.set_compact(False)

    def _on_clicked(self, _checked: bool = False) -> None:
        self.action.trigger()
        self.sync()

    def sync(self) -> None:
        """action의 활성/체크/보임 상태와 툴팁을 버튼에 옮긴다."""
        a = self.action
        self.setEnabled(a.isEnabled())
        self.setVisible(a.isVisible())
        if a.isCheckable():
            self.setCheckable(True)
            if self.isChecked() != a.isChecked():
                self.setChecked(a.isChecked())
        self.setToolTip(action_tooltip(a, self.full_text))

    def set_compact(self, compact: bool) -> None:
        if compact and not self.keep_text and self.icon_name:
            self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        elif self.icon_name:
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        else:
            self.setToolButtonStyle(Qt.ToolButtonTextOnly)


def action_tooltip(action: QAction, text: str | None = None) -> str:
    """'긴 설명 (단축키)' 형식 툴팁 (action.toolTip이 따로 있으면 그것을 설명으로)."""
    desc = action.toolTip() or text or action.text()
    desc = desc.replace("&", "")
    # QAction.toolTip() 기본값은 글자에서 '...'를 뺀 것 — 그대로 쓴다
    sc = action.shortcut().toString(QKeySequence.NativeText)
    return f"{desc} ({sc})" if sc else desc


class CommandBar(QToolBar):
    """메뉴 버튼 + 명령 버튼 한 줄 막대 (메인 윈도우의 유일한 도구 모음)."""

    language_selected = Signal(str)

    COMPACT_WIDTH = 1400
    """창 폭이 이보다 작으면 아이콘만 표시 (글자가 긴 언어는 전체 글자 폭이 기준 — full_width)."""

    def __init__(self, parent=None) -> None:
        super().__init__(tr("명령 막대"), parent)
        self.setObjectName("commandBar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setStyleSheet(build_bar_qss())
        self.menu_buttons: dict[str, QToolButton] = {}
        self.menu_shortcuts: dict[str, QShortcut] = {}
        self.action_buttons: dict[str, ActionButton] = {}
        self.dropdowns: dict[str, QToolButton] = {}
        self._dropdown_text: dict[str, str] = {}
        self.lang_button: QToolButton | None = None
        self.lang_actions: dict[str, QAction] = {}
        self._compact = False
        self._full_width: int | None = None     # 글자를 모두 보일 때 필요한 폭 (처음 필요할 때 잰다)

    # ------------------------------------------------------------------
    # 구성
    # ------------------------------------------------------------------
    def add_menu_button(self, key: str, text: str, menu: QMenu, mnemonic: str | None = None) -> QToolButton:
        """메뉴 버튼 (누르면 바로 menu를 펼친다). mnemonic='F' → Alt+F로 연다."""
        btn = QToolButton(self)
        btn.setObjectName(f"menuButton_{key}")
        btn.setProperty("role", "menu")
        btn.setText(text)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setAutoRaise(True)
        if mnemonic:
            seq = QKeySequence(f"Alt+{mnemonic}")
            btn.setToolTip(f"{text} ({seq.toString(QKeySequence.NativeText)})")
            sc = QShortcut(seq, self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(btn.showMenu)
            sc.activatedAmbiguously.connect(btn.showMenu)
            self.menu_shortcuts[key] = sc
        self.addWidget(btn)
        self.menu_buttons[key] = btn
        self._full_width = None
        return btn

    def add_action_button(self, key: str, action: QAction, text: str, icon_name: str | None = None, *,
                          primary: bool = False, keep_text: bool = False) -> ActionButton:
        btn = ActionButton(action, text, icon_name, primary=primary, keep_text=keep_text, parent=self)
        btn.setObjectName(f"commandButton_{key}")
        btn.setIconSize(QSize(16, 16) if primary else QSize(18, 18))
        btn.set_compact(self._compact)
        self.addWidget(btn)
        self.action_buttons[key] = btn
        self._full_width = None
        return btn

    def add_dropdown(self, key: str, text: str, icon_name: str | None, menu: QMenu,
                     tooltip: str = "") -> QToolButton:
        """아이콘 + 글자 + ▾ 드롭다운 (예: 내보내기)."""
        btn = QToolButton(self)
        btn.setObjectName(f"dropdown_{key}")
        btn.setProperty("role", "action")
        btn.setText(f"{_GAP if icon_name else ''}{text} ▾")
        if icon_name:
            btn.setIcon(icon(icon_name, theme.TEXT_2, 18))
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setAutoRaise(True)
        btn.setToolTip(tooltip or text)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly if self._compact else Qt.ToolButtonTextBesideIcon)
        self.addWidget(btn)
        self.dropdowns[key] = btn
        self._dropdown_text[key] = text
        self._full_width = None
        return btn

    def add_stretch(self) -> QWidget:
        w = QWidget(self)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.addWidget(w)
        return w

    def add_language_button(self, current: str = "ko") -> QToolButton:
        """언어 선택 (한국어/English). 고르면 language_selected(code)."""
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for code, _short, name in LANGUAGES:
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setData(code)
            group.addAction(act)
            act.triggered.connect(lambda _c=False, c=code: self._on_language(c))
            self.lang_actions[code] = act
        btn = QToolButton(self)
        btn.setObjectName("languageButton")
        btn.setProperty("role", "action")
        btn.setIcon(icon("languages", theme.TEXT_2, 18))
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setAutoRaise(True)
        btn.setToolTip(tr("화면 언어"))
        self.addWidget(btn)
        self.lang_button = btn
        self._full_width = None
        self.set_language(current)
        return btn

    def set_language(self, code: str) -> None:
        """언어 버튼 표시만 바꾼다 (신호 없음)."""
        short = next((s for c, s, _n in LANGUAGES if c == code), code.upper())
        if self.lang_button is not None:
            self.lang_button.setText(f"{_GAP}{short} ▾")
        act = self.lang_actions.get(code)
        if act is not None:
            act.setChecked(True)

    def _on_language(self, code: str) -> None:
        self.set_language(code)
        self.language_selected.emit(code)

    # ------------------------------------------------------------------
    # 폭에 따른 표시
    # ------------------------------------------------------------------
    @property
    def compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool) -> None:
        """True: 아이콘만 (주 버튼·메뉴·언어 버튼은 글자 유지)."""
        self._compact = bool(compact)
        for b in self.action_buttons.values():
            b.set_compact(self._compact)
        for b in self.dropdowns.values():
            b.setToolButtonStyle(Qt.ToolButtonIconOnly if self._compact else Qt.ToolButtonTextBesideIcon)

    def full_width(self) -> int:
        """
        모든 버튼에 글자를 보일 때 막대에 필요한 폭 (sizeHint). 영어처럼 글자가 길면 COMPACT_WIDTH보다
        클 수 있어, 이보다 좁으면 아이콘만 보여 오른쪽 버튼(언어)이 넘침 메뉴(») 속으로 숨지 않게 한다.
        """
        if self._full_width is None:
            was = self._compact
            if was:
                self.set_compact(False)
            self._full_width = int(self.sizeHint().width())
            if was:
                self.set_compact(True)
        return self._full_width

    def update_for_width(self, width: int) -> None:
        compact = width < max(self.COMPACT_WIDTH, self.full_width())
        if compact != self._compact:
            self.set_compact(compact)


__all__ = ["ActionButton", "CommandBar", "LANGUAGES", "action_tooltip", "build_bar_qss"]
