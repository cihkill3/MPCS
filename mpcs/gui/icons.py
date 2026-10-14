"""
MPCS — MALDI Polymer Composition Solver
GUI Layer: 아이콘 (Lucide SVG → 색을 입힌 QIcon)

mpcs/assets/icons/*.svg 는 Lucide(lucide-static 1.51.0, ISC 라이선스 — LICENSE-lucide.txt)의
원본 파일이다. SVG의 stroke="currentColor"를 요청한 색으로 바꿔 그린다.

    icon("play")                         보통 상태 TEXT_2, 비활성 REJECTED, 마우스 오버 ACCENT
    icon("play", color=theme.SURFACE)    주 버튼(채운 바탕) 위 흰 아이콘
    icon("panel-left", checked_color=theme.ACCENT)   눌림(On) 상태 색

같은 인자로 다시 부르면 캐시된 QIcon을 돌려준다. 파일이 없으면 빈 QIcon (예외 없음).
QApplication이 있어야 한다 (QPixmap).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from qtpy.QtCore import QByteArray, QRectF, Qt
from qtpy.QtGui import QIcon, QPainter, QPixmap

from mpcs.gui import theme

ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


@lru_cache(maxsize=None)
def _svg_text(name: str) -> str:
    """아이콘 SVG 원문 (없으면 빈 문자열)."""
    try:
        return (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    except OSError:
        return ""


def has_icon(name: str) -> bool:
    return bool(_svg_text(name))


def available_icons() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = theme.TEXT_2, size: int = 18, scale: float = 1.0) -> QPixmap:
    """name 아이콘을 color로 칠한 size×size 픽스맵 (scale = 장치 픽셀 비율)."""
    from qtpy.QtSvg import QSvgRenderer

    px = max(1, int(round(size * scale)))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    text = _svg_text(name)
    if not text:
        return pm
    data = text.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(data.encode("utf-8")))
    if not renderer.isValid():
        return pm
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


@lru_cache(maxsize=512)
def icon(name: str, color: str = theme.TEXT_2, size: int = 18, *,
         disabled_color: str = theme.REJECTED, active_color: str | None = theme.ACCENT,
         checked_color: str | None = None) -> QIcon:
    """
    색을 입힌 QIcon (보통/비활성/오버/눌림 상태별 픽스맵, 1×·2× 해상도).

    active_color   마우스 오버(QIcon.Active) 색. None이면 color와 같다.
    checked_color  체크된(On) 상태 색. None이면 상태별 색과 같다.
    """
    ic = QIcon()
    if not has_icon(name):
        return ic
    states = ((QIcon.Normal, color), (QIcon.Disabled, disabled_color),
              (QIcon.Active, active_color or color), (QIcon.Selected, active_color or color))
    for scale in (1.0, 2.0):
        for mode, col in states:
            ic.addPixmap(pixmap(name, col, size, scale), mode, QIcon.Off)
            on_col = checked_color if (checked_color and mode != QIcon.Disabled) else col
            ic.addPixmap(pixmap(name, on_col, size, scale), mode, QIcon.On)
    return ic


__all__ = ["APP_ICON_DIR", "ICON_DIR", "app_icon", "app_pixmap", "available_icons", "has_icon", "icon", "pixmap"]


APP_ICON_DIR = ICON_DIR.parent / "app_icon"


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """MPCS 앱 아이콘 (창 제목 표시줄·작업 표시줄·대화상자). packaging/make_icon.py가 만든 PNG들."""
    ic = QIcon()
    for p in sorted(APP_ICON_DIR.glob("mpcs_*.png")):
        ic.addFile(str(p))
    return ic


def app_pixmap(size: int = 64) -> QPixmap:
    """시작 화면·정보 창에 넣을 앱 아이콘 그림."""
    return app_icon().pixmap(size, size)
