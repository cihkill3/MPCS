"""
MPCS — 앱 아이콘 생성

청록 둥근 사각형 위에 고분자 MALDI 스펙트럼처럼 '주기적으로 반복되는 피크 시리즈'를 흰 막대로 그리고,
조성 계열로 지정된 피크 하나를 주황 막대 + ▲로 강조한다.

출력:
    packaging/mpcs.ico                 실행파일 아이콘 (16–256 px 여러 크기, PNG 프레임)
    mpcs/assets/app_icon/mpcs_{N}.png  창 아이콘 (실행 중 제목 표시줄·작업 표시줄·시작 화면)

실행:
    .venv2/Scripts/python.exe packaging/make_icon.py
"""

from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt5")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qtpy.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from qtpy.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

from mpcs.gui import theme  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256)
BG_TOP = QColor(theme.ACCENT)          # #0B7285
BG_BOTTOM = QColor("#08525F")
BAR = QColor("#FFFFFF")
HIGHLIGHT = QColor("#FFB04A")          # 청록 바탕에서 잘 보이는 밝은 주황 (theme.FAMILY_HL 계열)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 배경: 세로 그라데이션 둥근 사각형
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    r = size * 0.2
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)

    # 막대 수·굵기는 크기에 따라 (작은 아이콘은 단순하게)
    n = 5 if size <= 20 else (7 if size <= 40 else 9)
    margin = size * (0.16 if size > 20 else 0.14)
    base_y = size * (0.80 if size > 20 else 0.82)
    top_y = size * (0.30 if size >= 32 else 0.20)
    width = size - 2 * margin
    step = width / (n - 1)
    bar_w = max(1.6, step * (0.42 if size >= 64 else 0.55))
    hi = n // 2 + (1 if n >= 7 else 0)            # 강조 피크 (봉우리 바로 오른쪽)
    center = (n - 1) / 2

    for i in range(n):
        x = margin + i * step
        env = math.exp(-0.5 * ((i - center) / (n / 4.2)) ** 2)   # 포락선
        h = (base_y - top_y) * (0.18 + 0.82 * env)
        color = HIGHLIGHT if i == hi else BAR
        p.setBrush(color)
        p.drawRoundedRect(QRectF(x - bar_w / 2, base_y - h, bar_w, h), bar_w * 0.3, bar_w * 0.3)
        if i == hi and size >= 32:
            # ▲ 표시 (결과 화면의 계열 강조와 같은 기호)
            t = bar_w * 1.25
            tip_y = base_y - h - size * 0.045
            path = QPainterPath(QPointF(x, tip_y - t))
            path.lineTo(QPointF(x - t * 0.9, tip_y))
            path.lineTo(QPointF(x + t * 0.9, tip_y))
            path.closeSubpath()
            p.drawPath(path)

    # 기준선
    pen = QPen(QColor(255, 255, 255, 200))
    pen.setWidthF(max(1.0, size * 0.035))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(margin * 0.7, base_y + pen.widthF()), QPointF(size - margin * 0.7, base_y + pen.widthF()))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def write_ico(path: Path) -> None:
    """PNG 프레임 여러 개를 ICO 컨테이너로 묶는다 (Qt ico 플러그인은 한 이미지만 씀)."""
    frames = [(s, png_bytes(render(s))) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries, data = b"", b""
    offset = 6 + 16 * len(frames)
    for s, png in frames:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    path.write_bytes(header + entries + data)


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    ico = ROOT / "packaging" / "mpcs.ico"
    write_ico(ico)
    out_dir = ROOT / "mpcs" / "assets" / "app_icon"
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in PNG_SIZES:
        render(s).save(str(out_dir / f"mpcs_{s}.png"))
    print(ico)
    print(out_dir)


if __name__ == "__main__":
    main()
