"""
MPCS — GUI Panels: Spectrum Panel (mzXML → 피크 검출 → 주기 시리즈)

좌측 탭. 스펙트럼 파일을 열고 피크 검출 파라미터를 정한 뒤 [피크 검출]을 누르면
검출 결과가 우측 피크 목록/스펙트럼 플롯으로 전달된다.

Reflectron / Linear 프리셋은 피크 검출 파라미터와 함께 솔버의 질량 기준(Exact/Average)과
허용 오차도 맞춘다.
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mpcs.core.i18n import tr
from mpcs.infrastructure.file_io import FileImportError
from mpcs.infrastructure.spectrum_io import SPECTRUM_FILE_FILTER, read_spectrum_file
from mpcs.models.spectrum import PickedPeak, Spectrum, SpectrumFile
from mpcs.services.spectrum_processing import PeakPickingParams, pick_peaks

_PRESETS = {
    # name: (smooth, min_dist, deisotope, baseline, snr, mass_type, tol)
    "reflectron": (5, 0.3, "mono", 0.0, 5.0, "EXACT", 0.05),
    "linear": (15, 10.0, "none", 50.0, 5.0, "AVERAGE", 1.0),
}
_DEISO = [("none", "사용 안 함"), ("mono", "모노이소토픽만 (첫 피크)"), ("max", "최대 피크만")]


class SpectrumPanel(QWidget):
    """스펙트럼 열기 + 피크 검출 파라미터."""

    spectrum_loaded = Signal(object, str)          # Spectrum | None, 제목
    peaks_picked = Signal(list)                    # list[PickedPeak]
    preset_applied = Signal(str, float)            # mass_type, tolerance
    series_options_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._file: SpectrumFile | None = None
        self._spectrum: Spectrum | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)

        intro = QLabel(tr("질량값만 분석할 때는 오른쪽 피크 목록에 직접 입력/붙여넣기 하세요.\n"
                          "원본 스펙트럼(mzXML)을 열면 피크를 검출해 목록을 채웁니다."))
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555;")
        lay.addWidget(intro)

        # 파일
        file_box = QGroupBox(tr("스펙트럼 파일"))
        fl = QVBoxLayout(file_box)
        row = QHBoxLayout()
        open_btn = QPushButton(tr("mzXML 열기..."))
        open_btn.clicked.connect(self._browse)
        row.addWidget(open_btn)
        self._close_btn = QPushButton(tr("닫기"))
        self._close_btn.clicked.connect(self.close_spectrum)
        self._close_btn.setEnabled(False)
        row.addWidget(self._close_btn)
        row.addStretch()
        fl.addLayout(row)
        self._file_label = QLabel(tr("열린 파일 없음"))
        self._file_label.setWordWrap(True)
        fl.addWidget(self._file_label)
        self._scan_combo = QComboBox()
        self._scan_combo.setToolTip(tr("LC-MS: 스캔을 고르거나 MS1 전체를 합산합니다"))
        self._scan_combo.currentIndexChanged.connect(self._on_scan_changed)
        self._scan_combo.setVisible(False)
        fl.addWidget(self._scan_combo)
        lay.addWidget(file_box)

        # 프리셋
        preset_box = QGroupBox(tr("측정 모드 프리셋"))
        pl = QHBoxLayout(preset_box)
        for key, text, tip in [
            ("reflectron", tr("Reflectron / LC-MS"), tr("동위원소 분리: 모노이소토픽 피크 · 정밀질량 · 0.05 Da")),
            ("linear", tr("Linear"), tr("동위원소 미분리: 포락선 중심 · 평균질량 · 1 Da")),
        ]:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.apply_preset(k))
            pl.addWidget(b)
        lay.addWidget(preset_box)

        # 피크 검출 파라미터
        pick_box = QGroupBox(tr("피크 검출"))
        form = QFormLayout(pick_box)
        self._mz_min = self._dspin(0, 1e7, 0, 2, " Da", tr("0 = 자동"))
        self._mz_max = self._dspin(0, 1e7, 0, 2, " Da", tr("0 = 자동"))
        self._baseline = self._dspin(0, 5000, 0, 1, " Da", tr("베이스라인 추정 창 크기. 0 = 제거 안 함"))
        self._smooth = QSpinBox()
        self._smooth.setRange(0, 101)
        self._smooth.setSingleStep(2)
        self._smooth.setValue(5)
        self._smooth.setToolTip(tr("Savitzky–Golay 창 (점 수, 홀수). 0 = 사용 안 함"))
        self._snr = self._dspin(0, 1000, 5, 1, "", tr("신호 대 잡음비 임계값"))
        self._min_rel = self._dspin(0, 100, 0.5, 2, " %", tr("기준 피크 대비 최소 상대 강도"))
        self._min_dist = self._dspin(0, 1000, 0.3, 3, " Da", tr("이보다 가까운 피크는 강한 것만 남김"))
        self._max_peaks = QSpinBox()
        self._max_peaks.setRange(1, 10000)
        self._max_peaks.setValue(500)
        self._deiso = QComboBox()
        for key, text in _DEISO:
            self._deiso.addItem(tr(text), key)
        self._deiso.setCurrentIndex(1)
        for label, w in [("m/z 최소", self._mz_min), ("m/z 최대", self._mz_max), ("베이스라인 창", self._baseline),
                         ("스무딩", self._smooth), ("S/N ≥", self._snr), ("상대 강도 ≥", self._min_rel),
                         ("최소 간격", self._min_dist), ("최대 피크 수", self._max_peaks), ("동위원소 정리", self._deiso)]:
            form.addRow(tr(label), w)
        self._pick_btn = QPushButton(tr("▶ 피크 검출"))
        self._pick_btn.setEnabled(False)
        self._pick_btn.clicked.connect(self.run_peak_picking)
        form.addRow(self._pick_btn)
        lay.addWidget(pick_box)

        # 시리즈
        series_box = QGroupBox(tr("주기 시리즈 (반복단위 간격)"))
        sf = QFormLayout(series_box)
        self._min_len = QSpinBox()
        self._min_len.setRange(2, 100)
        self._min_len.setValue(4)
        self._min_len.setToolTip(tr("이 개수 이상 이어져야 시리즈로 인정"))
        self._max_gap = QSpinBox()
        self._max_gap.setRange(0, 5)
        self._max_gap.setValue(1)
        self._max_gap.setToolTip(tr("시리즈 안에서 건너뛸 수 있는 반복단위 수 (누락 피크 허용)"))
        for w in (self._min_len, self._max_gap):
            w.valueChanged.connect(self.series_options_changed.emit)
        sf.addRow(tr("최소 길이"), self._min_len)
        sf.addRow(tr("최대 건너뜀"), self._max_gap)
        note = QLabel(tr("반복단위 질량은 모노머 탭의 일반 모노머에서, 허용 오차·질량 기준은 아래 솔버 설정에서 가져옵니다."))
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        sf.addRow(note)
        lay.addWidget(series_box)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #1f4e79;")
        lay.addWidget(self._info)
        lay.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll)

    @staticmethod
    def _dspin(lo, hi, val, dec, suffix, tip) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setToolTip(tip)
        return s

    # ------------------------------------------------------------------
    # 파일
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("스펙트럼 열기"), "", tr(SPECTRUM_FILE_FILTER))
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> bool:
        try:
            self._file = read_spectrum_file(path)
        except FileImportError as exc:
            QMessageBox.critical(self, tr("파일 열기 실패"), str(exc))
            return False
        scans = self._file.ms1_scans()
        self._scan_combo.blockSignals(True)
        self._scan_combo.clear()
        if len(scans) > 1:
            self._scan_combo.addItem(tr("MS1 전체 합산 ({n}개 스캔)", n=len(scans)), -1)
        for i, s in enumerate(scans):
            self._scan_combo.addItem(s.label(), i)
        self._scan_combo.setVisible(len(scans) > 1)
        self._scan_combo.blockSignals(False)
        self._close_btn.setEnabled(True)
        self._pick_btn.setEnabled(True)
        self._file_label.setText(f"<b>{Path(path).name}</b><br>{len(self._file.scans)} {tr('스캔')}")
        self._on_scan_changed()
        return True

    def _on_scan_changed(self) -> None:
        if self._file is None:
            return
        scans = self._file.ms1_scans()
        idx = self._scan_combo.currentData()
        self._spectrum = self._file.combine(scans) if idx in (None, -1) and len(scans) > 1 else scans[max(idx or 0, 0)]
        sp = self._spectrum
        if sp.size and self._mz_min.value() == 0 and self._mz_max.value() == 0:
            self._info.setText(f"m/z {sp.mz.min():.1f} – {sp.mz.max():.1f}, {sp.size:,} {tr('점')}")
        self.spectrum_loaded.emit(sp, f"{Path(self._file.path).name} — {sp.label()}")

    def close_spectrum(self) -> None:
        self._file, self._spectrum = None, None
        self._scan_combo.clear()
        self._scan_combo.setVisible(False)
        self._close_btn.setEnabled(False)
        self._pick_btn.setEnabled(False)
        self._file_label.setText(tr("열린 파일 없음"))
        self._info.setText("")
        self.spectrum_loaded.emit(None, "")

    def file_path(self) -> str | None:
        return self._file.path if self._file else None

    # ------------------------------------------------------------------
    # 피크 검출
    # ------------------------------------------------------------------

    def apply_preset(self, key: str) -> None:
        smooth, dist, deiso, base, snr, mass_type, tol = _PRESETS[key]
        self._smooth.setValue(smooth)
        self._min_dist.setValue(dist)
        self._baseline.setValue(base)
        self._snr.setValue(snr)
        self._deiso.setCurrentIndex([k for k, _ in _DEISO].index(deiso))
        self.preset_applied.emit(mass_type, tol)

    def picking_params(self) -> PeakPickingParams:
        return PeakPickingParams(
            mz_min=self._mz_min.value() or None,
            mz_max=self._mz_max.value() or None,
            baseline_window_da=self._baseline.value(),
            smooth_points=self._smooth.value(),
            snr=self._snr.value(),
            min_rel_intensity=self._min_rel.value(),
            min_distance_da=self._min_dist.value(),
            max_peaks=self._max_peaks.value(),
            deisotope=self._deiso.currentData(),
        )

    def run_peak_picking(self) -> list[PickedPeak]:
        if self._spectrum is None:
            return []
        peaks = pick_peaks(self._spectrum, self.picking_params())
        self.peaks_picked.emit(peaks)
        return peaks

    def series_options(self) -> tuple[int, int]:
        return self._min_len.value(), self._max_gap.value()

    def set_info(self, text: str) -> None:
        self._info.setText(text)

    def current_spectrum(self) -> Spectrum | None:
        return self._spectrum


def peaks_to_rows(peaks: list[PickedPeak]) -> list[tuple[float, float, float, str]]:
    return [(p.mz, p.intensity, p.snr, f"iso×{p.isotope_cluster_size}" if p.isotope_cluster_size > 1 else "")
            for p in peaks]


__all__ = ["SpectrumPanel", "peaks_to_rows"]
