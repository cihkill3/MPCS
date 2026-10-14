"""
MPCS — MALDI Polymer Composition Solver
Infrastructure Layer: Spectrum File I/O (mzXML)

mzXML 2.x / 3.x 판독기 (외부 의존성 없음: xml.etree + base64 + zlib).
    <scan num msLevel retentionTime="PT12.3S" centroided polarity>
        <peaks precision="32|64" byteOrder="network"
               contentType|pairOrder="m/z-int" compressionType="none|zlib">BASE64</peaks>
    </scan>
중첩 스캔(MS2가 MS1 안에 있는 구조)도 지원한다.

보조로 2열(m/z, intensity) 텍스트(.txt/.csv/.xy)도 읽는다.
"""

from __future__ import annotations

from mpcs.core.i18n import tr
import base64
import re
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np

from mpcs.infrastructure.file_io import FileImportError
from mpcs.models.spectrum import Spectrum, SpectrumFile



def read_spectrum_file(path: str | Path) -> SpectrumFile:
    """확장자에 따라 mzXML 또는 2열 텍스트 스펙트럼을 읽는다."""
    p = Path(path)
    if not p.exists():
        raise FileImportError(str(p), tr("파일이 존재하지 않습니다"))
    try:
        if p.suffix.lower() == ".mzxml":
            return read_mzxml(p)
        return read_text_spectrum(p)
    except FileImportError:
        raise
    except Exception as exc:
        raise FileImportError(str(p), str(exc)) from exc


def read_mzxml(path: str | Path) -> SpectrumFile:
    """mzXML 파일의 모든 스캔을 읽는다."""
    p = Path(path)
    scans: list[Spectrum] = []
    for _event, elem in ET.iterparse(str(p), events=("end",)):
        if _local(elem.tag) != "scan":
            continue
        peaks_el = next((c for c in elem if _local(c.tag) == "peaks"), None)
        mz, it = _decode_peaks(peaks_el, int(elem.get("peaksCount") or -1))
        scans.append(Spectrum(
            mz=mz,
            intensity=it,
            centroided=elem.get("centroided", "0") in ("1", "true"),
            scan_num=int(elem.get("num")) if elem.get("num") else None,
            ms_level=int(elem.get("msLevel", "1") or 1),
            rt_sec=_parse_rt(elem.get("retentionTime")),
            polarity=elem.get("polarity"),
        ))
        # 자식 scan은 이미 처리됨. peaks 데이터만 해제해 메모리 절약
        if peaks_el is not None:
            peaks_el.text = None
    if not scans:
        raise FileImportError(str(p), tr("mzXML에서 scan을 찾을 수 없습니다"))
    scans.sort(key=lambda s: (s.scan_num is None, s.scan_num or 0))
    return SpectrumFile(path=str(p), scans=scans)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_rt(text: str | None) -> float | None:
    """'PT12.34S' / 'PT1M2.5S' / '12.3' → 초."""
    if not text:
        return None
    m = re.fullmatch(r"P?T?(?:(\d+(?:\.\d*)?)H)?(?:(\d+(?:\.\d*)?)M)?(?:(\d+(?:\.\d*)?)S)?", text.strip())
    if m and any(m.groups()):
        h, mi, s = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mi * 60 + s
    try:
        return float(text)
    except ValueError:
        return None


def _decode_peaks(el, peaks_count: int) -> tuple[np.ndarray, np.ndarray]:
    if el is None or peaks_count == 0 or not (el.text or "").strip():
        return np.zeros(0), np.zeros(0)
    raw = base64.b64decode("".join(el.text.split()))
    if (el.get("compressionType") or "none").lower() == "zlib":
        raw = zlib.decompress(raw)
    precision = int(el.get("precision", "32"))
    order = ">" if (el.get("byteOrder") or "network").lower() in ("network", "big") else "<"
    data = np.frombuffer(raw, dtype=f"{order}f{precision // 8}").astype(float)
    pair = (el.get("contentType") or el.get("pairOrder") or "m/z-int").lower()
    if data.size % 2:
        raise ValueError(tr("peaks 데이터 길이가 홀수입니다"))
    pairs = data.reshape(-1, 2)
    if pair.startswith("int"):
        return pairs[:, 1].copy(), pairs[:, 0].copy()
    return pairs[:, 0].copy(), pairs[:, 1].copy()


def read_text_spectrum(path: str | Path) -> SpectrumFile:
    """2열 텍스트 스펙트럼 (구분자 자동, 헤더/주석 무시)."""
    p = Path(path)
    content = None
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            content = p.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise FileImportError(str(p), tr("파일 인코딩을 인식할 수 없습니다"))
    mz, it = [], []
    for line in content.splitlines():
        line = line.strip()
        if not line or not (line[0].isdigit() or line[0] in "+-."):
            continue
        # 소수점 쉼표(유럽식) "1234,56;789,1" 처리
        if ";" in line and "," in line:
            line = line.replace(",", ".")
        cells = [c for c in re.split(r"[\t,; ]+", line) if c]
        if len(cells) < 2:
            continue
        try:
            mz.append(float(cells[0]))
            it.append(float(cells[1]))
        except ValueError:
            continue
    if not mz:
        raise FileImportError(str(p), tr("숫자 데이터(m/z, intensity)를 찾을 수 없습니다"))
    return SpectrumFile(path=str(p), scans=[Spectrum(np.array(mz), np.array(it))])


def write_mzxml(spectra: list[Spectrum], path: str | Path, compress: bool = True) -> None:
    """간단한 mzXML 3.2 작성기 (테스트 및 데모 데이터 생성용)."""
    lines = [
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
        '<mzXML xmlns="http://sashimi.sourceforge.net/schema_revision/mzXML_3.2">',
        f'  <msRun scanCount="{len(spectra)}">',
    ]
    for i, s in enumerate(spectra, start=1):
        data = np.column_stack([s.mz, s.intensity]).astype(">f4").tobytes()
        if compress:
            data = zlib.compress(data)
        b64 = base64.b64encode(data).decode("ascii")
        rt = f' retentionTime="PT{s.rt_sec:.3f}S"' if s.rt_sec is not None else ""
        lines.append(
            f'    <scan num="{s.scan_num or i}" msLevel="{s.ms_level}" peaksCount="{s.size}"'
            f' centroided="{1 if s.centroided else 0}" polarity="{s.polarity or "+"}"{rt}>'
        )
        lines.append(
            f'      <peaks precision="32" byteOrder="network" contentType="m/z-int"'
            f' compressionType="{"zlib" if compress else "none"}"'
            f' compressedLen="{len(data) if compress else 0}">{b64}</peaks>'
        )
        lines.append("    </scan>")
    lines += ["  </msRun>", "</mzXML>"]
    Path(path).write_text("\n".join(lines), encoding="ISO-8859-1")
