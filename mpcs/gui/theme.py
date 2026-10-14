"""
MPCS — MALDI Polymer Composition Solver
GUI Layer: 테마 토큰 (밝은 과학용 단일 테마)

모든 색·글꼴·간격은 이 모듈의 토큰에서 가져온다. 뷰 코드에 색 hex를 직접 쓰지 않는다.
어두운 테마는 지원하지 않는다 (결정 사항).

앱 적용: apply_theme(app) — Fusion + 팔레트(build_palette) + 앱 글꼴 + QSS(build_qss) + 표/트리 자동 손질.
뷰 코드는 토큰·헬퍼와 QSS 역할 이름(build_qss 설명 참조)만 쓴다.
"""

from __future__ import annotations

import math
from typing import Final

# ----------------------------------------------------------------------
# 색 토큰 (대비는 흰 바탕 기준 WCAG AA 이상)
# ----------------------------------------------------------------------
BG: Final = "#F4F5F7"            # 창 바탕
SURFACE: Final = "#FFFFFF"       # 패널·표 바탕
ZEBRA: Final = "#F8F9FB"         # 표 줄무늬
BORDER: Final = "#E2E5EA"        # 가는 구분선
BORDER_STRONG: Final = "#C9CED6" # 입력칸 테두리
TEXT: Final = "#1A1D23"          # 본문 15.9:1
TEXT_2: Final = "#454C57"        # 보조 8.6:1
TEXT_3: Final = "#666D78"        # 흐린 글자 5.4:1
ACCENT: Final = "#0B7285"        # 단일 강조색 (청록) 5.6:1
ACCENT_SOFT: Final = "#E3F3F5"   # 선택 행 / 강조 바탕
ACCENT_HOVER: Final = "#095C6B"

# 데이터 색 — Okabe–Ito 계열을 흰 바탕 4.5:1 이상으로 어둡게 (색약 친화)
SERIES_COLORS: Final[tuple[str, ...]] = (
    "#0072B2", "#007E66", "#6A3D9A", "#C04F00", "#8C6D1F", "#3F6E9E", "#7A4E7E", "#2F6F4F",
)
"""주기 시리즈 S1, S2, … 색 (순환)."""
NO_SERIES: Final = "#9AA1AB"     # 시리즈에 속하지 않은 피크
FAMILY_HL: Final = "#C04F00"     # 선택한 조성 계열의 피크 강조 (▲ + 반복수)
FAMILY_HL_BG: Final = "#FFF1E6"  # 계열 피크 행 바탕
SPECTRUM_LINE: Final = "#5C6670" # 스펙트럼 선
UNKNOWN: Final = "#4F5661"
REJECTED: Final = "#9AA1AB"

# 상태 색 — 빨강은 오류·실패에만 쓴다
BAD: Final = "#B42318"
WARN: Final = "#B54708"
GOOD: Final = "#1D7A46"
BAD_SOFT: Final = "#FDF0EF"
WARN_SOFT: Final = "#FFF6E8"
GOOD_SOFT: Final = "#ECF7F0"


def series_color(series_id: int | None) -> str:
    """시리즈 번호(1부터) → 색. None/0이면 NO_SERIES."""
    if not series_id:
        return NO_SERIES
    return SERIES_COLORS[(series_id - 1) % len(SERIES_COLORS)]


# ----------------------------------------------------------------------
# 글꼴 · 크기 · 간격
# ----------------------------------------------------------------------
FONT_FAMILY: Final = "Malgun Gothic"   # 한글·영문 단일 글꼴 (혼용 시 한글이 굵게 렌더링됨)
MONO_FAMILY: Final = "Consolas"        # 서열 입력·정렬이 필요한 숫자

FS_CAPTION: Final = 12   # 표 머리·캡션
FS_BODY: Final = 13      # 본문·표
FS_SECTION: Final = 13   # 구획 제목 (semibold)
FS_TITLE: Final = 14     # 패널 제목 (semibold)
FS_HERO: Final = 20      # 결과 요약 띠 등 핵심 숫자

SP_1: Final = 4
SP_2: Final = 8
SP_3: Final = 12
SP_4: Final = 16
ROW_H: Final = 26        # 표 행 높이
RADIUS: Final = 4


def app_font(point_px: int = FS_BODY, bold: bool = False):
    """앱 기본 글꼴 (힌팅 끔 — FreeType에서 받침 있는 한글이 깨지는 문제 방지)."""
    from qtpy.QtGui import QFont

    f = QFont(FONT_FAMILY)
    f.setPixelSize(point_px)
    f.setHintingPreference(QFont.PreferNoHinting)
    if bold:
        f.setWeight(QFont.DemiBold)
    return f


def mono_font(point_px: int = FS_BODY):
    from qtpy.QtGui import QFont

    f = QFont(MONO_FAMILY)
    f.setStyleHint(QFont.Monospace)
    f.setPixelSize(point_px)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


# ----------------------------------------------------------------------
# 숫자 서식
# ----------------------------------------------------------------------
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def fmt_sci(v: float | None, digits: int = 3) -> str:
    """큰 수를 2.26×10⁸ 형식으로 (|v| < 10000이면 정수/소수 그대로)."""
    if v is None or not math.isfinite(v):
        return ""
    a = abs(v)
    if a < 10000:
        return f"{v:,.0f}" if a >= 100 or v == int(v) else f"{v:.{digits}g}"
    e = int(math.floor(math.log10(a)))
    m = v / 10 ** e
    return f"{m:.{max(digits - 1, 0)}f}×10{str(e).translate(_SUP)}"


def fmt_pct(v: float | None, digits: int = 1) -> str:
    """상대 강도 % (기준 피크 = 100)."""
    if v is None or not math.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def formula_html(formula: str) -> str:
    """C99H160N24O27S → C<sub>99</sub>H<sub>160</sub>… (QLabel rich text용)."""
    out = []
    for ch in formula:
        out.append(f"<sub>{ch}</sub>" if ch.isdigit() else ch)
    return "".join(out).replace("</sub><sub>", "")


# ======================================================================
# 앱 스타일 (WP1): 팔레트 · QSS · 표/트리 공통 손질
# ======================================================================
# 추가 토큰 (위 토큰과 같은 계열)
DISABLED: Final = "#9AA1AB"        # 비활성 글자
BORDER_HOVER: Final = "#AEB4BD"    # 버튼/스크롤바 hover 테두리
SCROLL_HANDLE: Final = "#CDD2D9"   # 스크롤바 손잡이
CHECK_BORDER: Final = "#8F96A1"    # 체크박스·라디오 테두리 (3:1 이상)
ACCENT_DISABLED: Final = "#9CC7CF" # 비활성 주 버튼
ACCENT_TINT_2: Final = "#EEF6F8"   # 약한 강조 바탕 (선택 행보다 연함)
ON_ACCENT: Final = "#FFFFFF"       # 강조색 위 글자
SELECTION: Final = "#D2EBEF"       # 표·트리·목록 선택 행

FS_DIALOG: Final = 16    # 대화상자 제목 (semibold)
INPUT_H: Final = 30      # 입력칸·버튼 높이 (28–32 px)
CELL_PAD: Final = 6      # 표 셀 좌우 여백 (QSS item padding과 같아야 함)
HEADER_PAD: Final = 8    # 표 머리 오른쪽 여백 (정렬 화살표 자리 포함)

# UI 아이콘(SVG) 폴더 — QSS에서 url(mpcsui:파일.svg)로 참조 (경로에 공백이 있어도 안전)
ICON_SEARCH_PREFIX: Final = "mpcsui"


def ui_icon_dir() -> str:
    """mpcs/assets/icons/ui 절대 경로."""
    from pathlib import Path

    return str(Path(__file__).resolve().parents[1] / "assets" / "icons" / "ui")


def _register_icon_path() -> None:
    from qtpy.QtCore import QDir

    QDir.setSearchPaths(ICON_SEARCH_PREFIX, [ui_icon_dir()])


def build_palette():
    """토큰 → QPalette (Fusion이 직접 그리는 부분도 테마 색을 쓰도록)."""
    from qtpy.QtGui import QColor, QPalette

    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: SURFACE, QPalette.AlternateBase: ZEBRA,
        QPalette.Text: TEXT, QPalette.Button: SURFACE, QPalette.ButtonText: TEXT,
        QPalette.Highlight: SELECTION, QPalette.HighlightedText: TEXT,
        QPalette.ToolTipBase: SURFACE, QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: TEXT_3,
        QPalette.Link: ACCENT, QPalette.LinkVisited: ACCENT_HOVER, QPalette.BrightText: BAD,
        QPalette.Light: SURFACE, QPalette.Midlight: BORDER, QPalette.Mid: BORDER_STRONG,
        QPalette.Dark: BORDER_HOVER, QPalette.Shadow: TEXT_3,
    }
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, color in roles.items():
            pal.setColor(group, role, QColor(color))
    dis = QPalette.Disabled
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.HighlightedText):
        pal.setColor(dis, role, QColor(DISABLED))
    for role in (QPalette.Base, QPalette.Button):
        pal.setColor(dis, role, QColor(BG))
    pal.setColor(dis, QPalette.Highlight, QColor(BORDER))
    return pal


def build_qss() -> str:
    """
    앱 전체 QSS. 본문 글꼴은 QSS에 쓰지 않는다 (위젯의 setFont()를 덮어쓰지 않도록 app.setFont로만).
    크기가 정해진 역할(표 머리, 역할 라벨)만 예외.

    역할(objectName) 약속 — 뷰 코드는 색을 직접 쓰지 말고 이 이름을 붙인다:
        QPushButton#primaryButton / QToolButton#primaryTool   주 동작 (강조색 채움)
        QLabel#dialogTitle   대화상자 제목 (16 px semibold)
        QLabel#panelTitle    패널·뷰 제목 (14 px semibold)
        QLabel#sectionTitle  구획 제목 (13 px semibold) — common.hline()과 함께
        QLabel#caption       캡션·설명 (12 px, TEXT_3)
        QLabel#keyValue      핵심 숫자 (20 px semibold)
        QLabel#emptyState    빈 상태 안내 (14 px, TEXT_3, 가운데)
        QLabel#legendItem    범례 (12 px, TEXT_2)
        QLabel#errorText / #warnText / #goodText   상태 글자색
        QFrame#rule          가는 구분선 (1 px BORDER)
        QWidget#viewHeader   뷰 머리 띠 (흰 바탕 + 아래 선)
    QDialogButtonBox의 기본(default) 버튼은 강조색 채움이 된다 (굵기·여백은 그대로 — 크기 계산 뒤 바뀌면 글자가 잘림).
    닫기만 있는 대화상자는 common.plain_close_box()로 강조 없는 닫기 버튼을 쓴다.
    """
    _register_icon_path()
    u = ICON_SEARCH_PREFIX
    r = RADIUS + 1
    inner_h = INPUT_H - 10      # 테두리 1 + 위아래 padding 4
    return f"""
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS}px; padding: 6px 8px; }}

QMainWindow {{ background: {BG}; }}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}
QDialog, QMessageBox {{ background: {SURFACE}; }}

/* --- 메뉴 / 툴바 / 상태바 --- */
QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: {RADIUS}px; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_HOVER}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 5px 28px 5px 14px; border-radius: {RADIUS}px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QToolBar {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER}; padding: 4px 8px;
    spacing: 2px; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 4px 8px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r}px;
    padding: 4px 8px; color: {TEXT_2}; }}
QToolButton:hover {{ background: {BG}; border-color: {BORDER}; color: {TEXT}; }}
QToolButton:pressed {{ background: {BORDER}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT_HOVER}; }}
QToolButton:disabled {{ color: {DISABLED}; }}
QToolButton#primaryTool {{ background: {ACCENT}; border-color: {ACCENT}; color: {ON_ACCENT}; font-weight: 600;
    padding: 4px 14px; }}
QToolButton#primaryTool:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QToolButton#primaryTool:disabled {{ background: {ACCENT_DISABLED}; border-color: {ACCENT_DISABLED}; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {TEXT_2}; }}
QStatusBar::item {{ border: none; }}

/* --- 구획: 테두리 상자 대신 제목 + 위쪽 가는 선 --- */
QGroupBox {{ background: transparent; border: none; border-top: 1px solid {BORDER};
    margin-top: 24px; padding-top: 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 0px; top: 2px;
    padding: 0; color: {TEXT}; }}
QFrame#rule {{ background: {BORDER}; border: none; min-height: 1px; max-height: 1px; }}

QScrollArea {{ background: {SURFACE}; border: none; }}
QScrollArea > QWidget > QWidget {{ background: {SURFACE}; }}

/* --- 버튼 --- */
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: {r}px;
    padding: 4px 12px; min-height: {inner_h}px; color: {TEXT}; }}
QPushButton:hover {{ background: {BG}; border-color: {BORDER_HOVER}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT_HOVER}; }}
QPushButton:disabled {{ background: {BG}; color: {DISABLED}; border-color: {BORDER}; }}
QPushButton#primaryButton {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {ON_ACCENT};
    font-weight: 600; padding: 4px 16px; }}
QDialogButtonBox QPushButton:default {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {ON_ACCENT}; }}
QPushButton#primaryButton:hover, QDialogButtonBox QPushButton:default:hover {{
    background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primaryButton:disabled, QDialogButtonBox QPushButton:default:disabled {{
    background: {ACCENT_DISABLED}; border-color: {ACCENT_DISABLED}; color: {ON_ACCENT}; }}
QPushButton::menu-indicator {{ image: url({u}:chev_down.svg); subcontrol-position: right center;
    subcontrol-origin: padding; width: 9px; right: 4px; }}

/* --- 입력 (높이 {INPUT_H} px) --- */
QLineEdit, QAbstractSpinBox, QComboBox {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG};
    border-radius: {r}px; padding: 4px 8px; min-height: {inner_h}px; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QPlainTextEdit, QTextEdit {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG};
    border-radius: {r}px; padding: 2px; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QLineEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {{ border-color: {BORDER_HOVER}; }}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled,
QTextEdit:disabled {{ background: {BG}; color: {DISABLED}; border-color: {BORDER}; }}
QLineEdit:read-only {{ background: {BG}; }}
QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 20px;
    border: none; border-left: 1px solid {BORDER}; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: {r}px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: {r}px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {BG}; }}
QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{ background: {BORDER}; }}
QAbstractSpinBox::up-arrow {{ image: url({u}:chev_up.svg); width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ image: url({u}:chev_down.svg); width: 9px; height: 9px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url({u}:chev_up_disabled.svg); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{
    image: url({u}:chev_down_disabled.svg); }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px;
    border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url({u}:chev_down.svg); width: 10px; height: 10px; }}
QComboBox::down-arrow:disabled {{ image: url({u}:chev_down_disabled.svg); }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; outline: 0;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; padding: 2px; }}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 0 6px; }}

/* --- 체크박스 / 라디오 --- */
QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; color: {TEXT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {DISABLED}; }}
QCheckBox::indicator, QGroupBox::indicator, QAbstractItemView::indicator {{ width: 14px; height: 14px;
    border: 1px solid {CHECK_BORDER}; border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QGroupBox::indicator:checked, QAbstractItemView::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({u}:check.svg); }}
QCheckBox::indicator:indeterminate, QAbstractItemView::indicator:indeterminate {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({u}:indeterminate.svg); }}
QCheckBox::indicator:disabled {{ background: {BG}; border-color: {BORDER}; }}
QCheckBox::indicator:checked:disabled {{ background: {ACCENT_DISABLED}; border-color: {ACCENT_DISABLED}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {CHECK_BORDER}; border-radius: 8px;
    background: {SURFACE}; }}
QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({u}:radio_dot.svg); }}
QRadioButton::indicator:disabled {{ background: {BG}; border-color: {BORDER}; }}

/* --- 표 / 트리 / 목록: 격자 없음, 줄무늬, 행 {ROW_H} px (polish_item_view) ---
   주의: ::item에 border/background를 쓰면 모델 BackgroundRole(행 강조 바탕)이 무시된다. padding만 쓴다. */
QAbstractItemView {{ background: {SURFACE}; alternate-background-color: {ZEBRA}; color: {TEXT};
    border: 1px solid {BORDER}; gridline-color: {BORDER}; outline: 0;
    selection-background-color: {SELECTION}; selection-color: {TEXT}; }}
QAbstractItemView:disabled {{ color: {DISABLED}; }}
QTableView::item {{ padding: 0px {CELL_PAD}px; }}
QTreeView::item {{ padding: 0px 4px; min-height: {ROW_H - 4}px; }}
QListView::item {{ padding: 3px 6px; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {SELECTION}; color: {TEXT}; }}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:selected {{ background: {SELECTION}; }}
QTreeView::branch:has-children:closed {{ image: url({u}:branch_closed.svg); }}
QTreeView::branch:has-children:open {{ image: url({u}:branch_open.svg); }}
/* 머리 위젯 글꼴도 ::section 과 같게 — Qt 는 머리 글자 말줄임·크기를 위젯 글꼴로 계산한다 (다르면 굵은 글자가 잘림) */
QHeaderView {{ background: {SURFACE}; border: none; font-weight: 600; font-size: {FS_CAPTION}px; }}
QHeaderView::section {{ background: {SURFACE}; color: {TEXT_2}; font-weight: 600; font-size: {FS_CAPTION}px;
    padding: 5px {HEADER_PAD}px 5px {CELL_PAD}px; border: none; border-bottom: 1px solid {BORDER_STRONG}; }}
QHeaderView::section:vertical {{ border-bottom: none; border-right: 1px solid {BORDER}; padding: 0 6px; }}
QHeaderView::section:hover {{ color: {TEXT}; }}
QHeaderView::down-arrow {{ image: url({u}:chev_down.svg); width: 8px; height: 8px; }}
QHeaderView::up-arrow {{ image: url({u}:chev_up.svg); width: 8px; height: 8px; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* --- 탭: 상자 대신 밑줄 --- */
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; background: {SURFACE}; top: -1px; }}
QTabWidget::tab-bar {{ left: 8px; }}
/* 굵기는 ::tab 이 아니라 QTabBar 자체에 준다 — Qt 는 탭 크기 계산에 ::tab 의 font 를 쓰지 않아
   굵은 글자가 양옆으로 잘린다. QTabBar 폰트로 주면 sizeHint 와 그리기가 같은 폰트를 쓴다. */
QTabBar {{ background: transparent; qproperty-drawBase: 0; font-weight: 600; }}
QTabBar::tab {{ background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 7px 14px 6px 14px; margin-right: 2px; color: {TEXT_3}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; border-bottom: 2px solid {BORDER_STRONG}; }}
QTabBar::tab:disabled {{ color: {DISABLED}; }}
QTabBar QToolButton {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 0; }}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}

/* --- 스크롤바 --- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {SCROLL_HANDLE}; border-radius: 3px; min-height: 28px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {SCROLL_HANDLE}; border-radius: 3px; min-width: 28px;
    margin: 2px; }}
QScrollBar::handle:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {BORDER}; border: none; border-radius: 3px; min-height: 6px; max-height: 6px;
    color: transparent; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

/* --- 역할 라벨 --- */
QLabel#dialogTitle {{ font-size: {FS_DIALOG}px; font-weight: 600; color: {TEXT}; }}
QLabel#panelTitle {{ font-size: {FS_TITLE}px; font-weight: 600; color: {TEXT}; }}
QLabel#sectionTitle {{ font-size: {FS_SECTION}px; font-weight: 600; color: {TEXT}; }}
QLabel#caption {{ font-size: {FS_CAPTION}px; color: {TEXT_3}; }}
QLabel#keyValue {{ font-size: {FS_HERO}px; font-weight: 600; color: {TEXT}; }}
QLabel#legendItem {{ font-size: {FS_CAPTION}px; color: {TEXT_2}; }}
QLabel#emptyState {{ font-size: 14px; color: {TEXT_3}; }}
QLabel#errorText {{ color: {BAD}; }}
QLabel#warnText {{ color: {WARN}; }}
QLabel#goodText {{ color: {GOOD}; }}
QWidget#viewHeader {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
"""


def polish_item_view(view, row_h: int = ROW_H) -> None:
    """
    표/트리 공통 손질: 격자 끄기, 줄무늬, 행 높이 row_h, 머리 왼쪽 정렬, 머리 강조 끔.
    apply_theme()가 모든 QTableView/QTreeView에 자동으로 적용한다.
    격자·행 높이를 직접 정하는 뷰는 setProperty("themeKeep", True)로 건너뛴다.
    """
    from qtpy.QtCore import Qt
    from qtpy.QtWidgets import QHeaderView, QTableView, QTreeView

    if view.property("themeKeep"):
        return
    if isinstance(view, QTableView):
        view.setAlternatingRowColors(True)
        view.setShowGrid(False)
        vh = view.verticalHeader()
        if vh.count() == 0 or vh.sectionResizeMode(0) != QHeaderView.ResizeToContents:
            vh.setDefaultSectionSize(row_h)
        hh = view.horizontalHeader()
    elif isinstance(view, QTreeView):
        view.setAlternatingRowColors(True)
        hh = view.header()
    else:
        return
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setHighlightSections(False)


def _make_view_polisher(parent):
    """앱 이벤트 필터: 표/트리가 처음 Polish될 때 polish_item_view를 한 번 적용한다."""
    from qtpy.QtCore import QEvent, QObject
    from qtpy.QtWidgets import QAbstractItemView

    polish = QEvent.Polish

    class ViewPolisher(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802
            if ev.type() == polish and isinstance(obj, QAbstractItemView) and not obj.property("_themed"):
                obj.setProperty("_themed", True)
                polish_item_view(obj)
            return False

    return ViewPolisher(parent)


def apply_theme(app) -> None:
    """
    QApplication에 MPCS 테마를 적용한다 (창을 만들기 전에 한 번).
    Fusion 스타일 + 토큰 팔레트 + 앱 글꼴(맑은 고딕, 힌팅 끔) + QSS + 표/트리 자동 손질 + pyqtgraph 기본색.
    여러 번 불러도 안전하다. (PepLCMS 테마에서 복사해 MPCS용으로 독립 관리)
    """
    from qtpy.QtWidgets import QStyleFactory, QToolTip

    style = QStyleFactory.create("Fusion")
    if style is not None:
        app.setStyle(style)
    pal = build_palette()
    app.setPalette(pal)
    QToolTip.setPalette(pal)
    f = app_font()
    app.setFont(f)
    QToolTip.setFont(f)
    app.setStyleSheet(build_qss())
    if getattr(app, "_mpcs_view_polisher", None) is None:
        pol = _make_view_polisher(app)
        app.installEventFilter(pol)
        app._mpcs_view_polisher = pol
    try:
        import pyqtgraph as pg

        pg.setConfigOptions(background=SURFACE, foreground=TEXT_2)
    except Exception:  # noqa: BLE001 — pyqtgraph가 없어도 테마는 적용
        pass
