"""
MPCS — MALDI Polymer Composition Solver
Infrastructure Layer: MALDI Peak File I/O

SRS §12.3 File Import: CSV, XLSX, TXT
SRS §12.4 Peak File Structure: m/z, Intensity 컬럼 필수

Q9 사용자 확인:
    구분자: 탭(\\t)
    헤더: 첫 번째 행이 헤더
    예시 형식 (CSV/TXT):
        m/z\\tIntensity
        15123.43\\t100.0
        15167.47\\t80.5
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

from mpcs.models.result import PeakData


# Q9: 탭 구분자 + 헤더
_DEFAULT_DELIMITER: Final[str] = "\t"

# 허용 열 이름 (대소문자 무시)
_MZ_COLUMN_ALIASES: Final[frozenset[str]] = frozenset({
    "m/z", "mz", "mass", "mass/charge", "m_z", "m-z",
})
_INTENSITY_COLUMN_ALIASES: Final[frozenset[str]] = frozenset({
    "intensity", "int", "intens", "abundance", "counts", "i",
})


class FileImportError(IOError):
    """파일 가져오기 오류."""

    def __init__(self, filepath: str, reason: str) -> None:
        self.filepath = filepath
        self.reason = reason
        super().__init__(f"파일 가져오기 실패 '{filepath}': {reason}")


class PeakFileIO:
    """
    MALDI 피크 파일 읽기/쓰기.

    SRS §12.3, §12.4 준수.
    Q9: 탭 구분자, 헤더 포함.

    지원 형식: CSV, TXT (탭 구분), XLSX
    필수 컬럼: m/z, Intensity (대소문자 무관)
    """

    @classmethod
    def read(cls, filepath: str | Path) -> PeakData:
        """
        피크 파일을 읽어 PeakData를 반환한다.

        Args:
            filepath: 파일 경로 (.csv, .txt, .xlsx)

        Returns:
            PeakData 인스턴스

        Raises:
            FileImportError: 파일 읽기/파싱 실패
        """
        path = Path(filepath)
        if not path.exists():
            raise FileImportError(str(filepath), f"파일이 존재하지 않습니다: {path}")

        suffix = path.suffix.lower()
        try:
            if suffix in (".csv", ".txt"):
                return cls._read_delimited(path)
            elif suffix in (".xlsx", ".xls"):
                return cls._read_excel(path)
            else:
                raise FileImportError(
                    str(filepath),
                    f"지원하지 않는 파일 형식: {suffix}. "
                    f"지원 형식: .csv, .txt, .xlsx"
                )
        except FileImportError:
            raise
        except Exception as exc:
            raise FileImportError(str(filepath), str(exc)) from exc

    @classmethod
    def _read_delimited(cls, path: Path) -> PeakData:
        """
        탭 구분 텍스트 파일 읽기 (CSV/TXT).

        Q9: 탭 구분자, 첫 행 헤더.
        """
        mz_values: list[float] = []
        intensities: list[float] = []

        encodings = ["utf-8", "utf-8-sig", "cp949", "euc-kr"]
        content: str | None = None

        for enc in encodings:
            try:
                content = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise FileImportError(str(path), "파일 인코딩을 인식할 수 없습니다")

        lines = content.splitlines()
        if not lines:
            raise FileImportError(str(path), "파일이 비어 있습니다")

        # 헤더 행 파싱
        reader = csv.reader(lines, delimiter=_DEFAULT_DELIMITER)
        rows = list(reader)

        if not rows:
            raise FileImportError(str(path), "데이터가 없습니다")

        header = [col.strip().lower() for col in rows[0]]
        mz_idx, int_idx = cls._find_column_indices(header, str(path))

        # 데이터 행 파싱 (헤더 제외)
        for line_num, row in enumerate(rows[1:], start=2):
            if not row or all(cell.strip() == "" for cell in row):
                continue  # 빈 행 무시

            try:
                mz = float(row[mz_idx].strip())
                intensity = float(row[int_idx].strip())
                mz_values.append(mz)
                intensities.append(intensity)
            except (ValueError, IndexError) as exc:
                raise FileImportError(
                    str(path),
                    f"행 {line_num}: 숫자 변환 실패 ({exc})"
                ) from exc

        if not mz_values:
            raise FileImportError(str(path), "유효한 피크 데이터가 없습니다")

        return PeakData(mz_values=mz_values, intensities=intensities)

    @classmethod
    def _read_excel(cls, path: Path) -> PeakData:
        """XLSX 파일 읽기 (첫 번째 시트, 첫 행 헤더)."""
        try:
            import openpyxl
        except ImportError as exc:
            raise FileImportError(
                str(path), "openpyxl 라이브러리가 필요합니다"
            ) from exc

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise FileImportError(str(path), "시트가 비어 있습니다")

        # 헤더
        header = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
        mz_idx, int_idx = cls._find_column_indices(header, str(path))

        mz_values: list[float] = []
        intensities: list[float] = []

        for line_num, row in enumerate(rows[1:], start=2):
            if all(cell is None for cell in row):
                continue
            try:
                mz = float(row[mz_idx])
                intensity = float(row[int_idx]) if row[int_idx] is not None else 0.0
                mz_values.append(mz)
                intensities.append(intensity)
            except (TypeError, ValueError) as exc:
                raise FileImportError(
                    str(path), f"행 {line_num}: 숫자 변환 실패 ({exc})"
                ) from exc

        wb.close()

        if not mz_values:
            raise FileImportError(str(path), "유효한 피크 데이터가 없습니다")

        return PeakData(mz_values=mz_values, intensities=intensities)

    @staticmethod
    def _find_column_indices(
        header: list[str], filepath: str
    ) -> tuple[int, int]:
        """
        헤더에서 m/z와 Intensity 컬럼 인덱스를 찾는다.

        Raises:
            FileImportError: 필수 컬럼을 찾을 수 없는 경우
        """
        mz_idx: int | None = None
        int_idx: int | None = None

        for i, col in enumerate(header):
            col_norm = col.replace(" ", "").replace("_", "")
            if col_norm in {a.replace(" ", "").replace("_", "") for a in _MZ_COLUMN_ALIASES}:
                mz_idx = i
            elif col_norm in {a.replace(" ", "").replace("_", "") for a in _INTENSITY_COLUMN_ALIASES}:
                int_idx = i

        if mz_idx is None:
            raise FileImportError(
                filepath,
                f"m/z 컬럼을 찾을 수 없습니다. "
                f"헤더: {header}. "
                f"허용 이름: {sorted(_MZ_COLUMN_ALIASES)}"
            )
        if int_idx is None:
            raise FileImportError(
                filepath,
                f"Intensity 컬럼을 찾을 수 없습니다. "
                f"헤더: {header}. "
                f"허용 이름: {sorted(_INTENSITY_COLUMN_ALIASES)}"
            )

        return mz_idx, int_idx

    @classmethod
    def write_txt(
        cls,
        peak_data: PeakData,
        filepath: str | Path,
    ) -> None:
        """
        PeakData를 탭 구분 텍스트 파일로 저장한다.

        Q9: 탭 구분자, 헤더 포함.
        """
        path = Path(filepath)
        lines = ["m/z\tIntensity"]
        for mz, intensity in zip(peak_data.mz_values, peak_data.intensities):
            lines.append(f"{mz}\t{intensity}")

        path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 관대한 피크 표 읽기 (엑셀 / CSV / TXT / 클립보드)
# ---------------------------------------------------------------------------

def parse_peak_rows(rows: list[list]) -> list[tuple[float, float | None, str]]:
    """
    셀 행 목록 → [(m/z, intensity|None, 메모)].

    헤더 행(m/z·intensity 별칭)이 있으면 그 열을 쓰고, 없으면
    첫 번째 숫자 열 = m/z, 두 번째 숫자 열 = intensity, 첫 번째 문자 열 = 메모로 본다.
    """
    def num(v) -> float | None:
        if v is None:
            return None
        try:
            f = float(str(v).strip().replace(",", ""))
            return f if f == f else None   # NaN 제외
        except ValueError:
            return None

    def norm(v) -> str:
        return str(v).strip().lower().replace(" ", "").replace("_", "") if v is not None else ""

    mz_aliases = {a.replace(" ", "").replace("_", "") for a in _MZ_COLUMN_ALIASES} | {"m/z(da)", "mass(da)", "질량"}
    int_aliases = {a.replace(" ", "").replace("_", "") for a in _INTENSITY_COLUMN_ALIASES} | {"강도"}

    mz_idx = int_idx = note_idx = None
    start = 0
    for i, row in enumerate(rows[:20]):
        names = [norm(c) for c in row]
        if any(n in mz_aliases for n in names):
            mz_idx = next(j for j, n in enumerate(names) if n in mz_aliases)
            int_idx = next((j for j, n in enumerate(names) if n in int_aliases), None)
            note_idx = next((j for j, n in enumerate(names) if n and j not in (mz_idx, int_idx)), None)
            start = i + 1
            break

    data = rows[start:]
    if mz_idx is None:
        width = max((len(r) for r in data), default=0)
        numeric_cols = [j for j in range(width)
                        if sum(num(r[j]) is not None for r in data if j < len(r)) >= max(1, len(data) // 2)]
        if not numeric_cols:
            return []
        mz_idx = numeric_cols[0]
        int_idx = numeric_cols[1] if len(numeric_cols) > 1 else None
        note_idx = next((j for j in range(width) if j not in numeric_cols), None)

    out: list[tuple[float, float | None, str]] = []
    for r in data:
        mz = num(r[mz_idx]) if mz_idx < len(r) else None
        if mz is None or mz <= 0:
            continue
        inten = num(r[int_idx]) if int_idx is not None and int_idx < len(r) else None
        note = str(r[note_idx]).strip() if note_idx is not None and note_idx < len(r) and r[note_idx] is not None else ""
        out.append((mz, inten, "" if note.lower() == "nan" else note))
    return out


def split_text_rows(text: str) -> list[list[str]]:
    """탭/쉼표/세미콜론/공백 구분 텍스트 → 셀 행 목록."""
    import re

    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        delim = "\t" if "\t" in line else (";" if ";" in line else ("," if "," in line else None))
        cells = line.split(delim) if delim else re.split(r"\s+", line.strip())
        rows.append([c.strip() for c in cells])
    return rows


def read_peak_table(filepath: str | Path) -> list[tuple[float, float | None, str]]:
    """엑셀(.xlsx/.xls) 또는 텍스트(.csv/.txt) 피크 표를 관대하게 읽는다."""
    path = Path(filepath)
    if not path.exists():
        raise FileImportError(str(path), "파일이 존재하지 않습니다")
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            import pandas as pd

            df = pd.read_excel(path, header=None, dtype=object)
            rows = df.where(df.notna(), None).values.tolist()
        else:
            content = None
            for enc in ("utf-8", "utf-8-sig", "cp949"):
                try:
                    content = path.read_text(encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                raise FileImportError(str(path), "파일 인코딩을 인식할 수 없습니다")
            rows = split_text_rows(content)
    except FileImportError:
        raise
    except Exception as exc:
        raise FileImportError(str(path), str(exc)) from exc
    peaks = parse_peak_rows(rows)
    if not peaks:
        raise FileImportError(str(path), "m/z 숫자 열을 찾을 수 없습니다")
    return peaks
