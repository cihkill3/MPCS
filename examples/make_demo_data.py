"""
MPCS 데모 데이터 생성.

PEG–PLA 공중합체(EO_n LA_m, 말단 H/OH)를 가정한 합성 MALDI 스펙트럼:
    계열 1: EO n=15–70, LA 5, [M+Na]+   (주 계열)
    계열 2: EO n=15–70, LA 3, [M+K]+    (부 계열)

생성 파일 (examples/):
    demo_reflectron.mzXML   분해능 12,000 (동위원소 분리) → 정밀질량
    demo_linear.mzXML       분해능 600 (동위원소 미분리)  → 평균질량
    demo_peaks.xlsx         질량값 목록 (엑셀 붙여넣기/가져오기 예시)
    demo_project.mpcs       모노머 EO/LA, 말단기 H/OH, 어덕트 Na/K/H

실행:
    .venv2/Scripts/python.exe examples/make_demo_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pandas as pd  # noqa: E402

from mpcs.core.mass_calculator import MassCalculator  # noqa: E402
from mpcs.infrastructure.project_serializer import ProjectSerializer  # noqa: E402
from mpcs.infrastructure.spectrum_io import write_mzxml  # noqa: E402
from mpcs.models.adduct import Adduct  # noqa: E402
from mpcs.models.end_group import EndGroup  # noqa: E402
from mpcs.models.monomer import Monomer, MonomerType  # noqa: E402
from mpcs.models.project import Project  # noqa: E402
from mpcs.models.result import PeakData  # noqa: E402
from mpcs.services.synthetic_spectrum import SeriesSpec, make_polymer_spectrum, series_sticks  # noqa: E402

SERIES = [
    SeriesSpec("C2H4O", "C15H22O11Na", 15, 70, 40, 8, 1.0),   # EOn LA5 + H/OH + Na
    SeriesSpec("C2H4O", "C9H14O7K", 15, 70, 35, 7, 0.5),      # EOn LA3 + H/OH + K
]


def main() -> None:
    write_mzxml([make_polymer_spectrum(SERIES, 1000, 4000, resolution=12000, seed=1)],
                HERE / "demo_reflectron.mzXML")
    write_mzxml([make_polymer_spectrum(SERIES, 1000, 4000, resolution=600, seed=2)],
                HERE / "demo_linear.mzXML")

    # 질량 목록: 주 계열 모노이소토픽 10개 + 메모
    monos: dict[int, float] = {}
    for mz, _i, n in series_sticks(SERIES[0]):
        monos.setdefault(n, mz)
    rows = [{"m/z": round(monos[n], 4), "Intensity": 100.0, "메모": f"sample A #{k + 1}"}
            for k, n in enumerate(range(30, 40))]
    pd.DataFrame(rows).to_excel(HERE / "demo_peaks.xlsx", index=False)

    calc = MassCalculator()
    project = Project(
        name="PEG-PLA demo",
        monomers=[
            Monomer.from_formula("EO", MonomerType.MONOMER, "C2H4O", calc, 0, 80),
            Monomer.from_formula("LA", MonomerType.MONOMER, "C3H4O2", calc, 0, 20),
        ],
        end_group=EndGroup("H/OH"),
        adducts=[Adduct("[M+H]+", enabled=True), Adduct("[M+Na]+", enabled=True), Adduct("[M+K]+", enabled=True)],
        peak_data=PeakData(mz_values=[r["m/z"] for r in rows], intensities=[100.0] * len(rows),
                           notes=[r["메모"] for r in rows]),
    )
    ProjectSerializer().save(project, HERE / "demo_project.mpcs")
    print("written:", *sorted(p.name for p in HERE.glob("demo_*")))


if __name__ == "__main__":
    main()
