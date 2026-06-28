"""
MPCS — MALDI Polymer Composition Solver
Core Layer: Atomic Monoisotopic Mass Database

SRS §6.3 Supported Elements:
    H, C, N, O, S, P, F, Cl, Br, I, Si, B, Na, K, Li, Mg, Ca, Zn

SRS §6.4 Atomic Mass Database:
    The program shall internally contain monoisotopic masses.

Data source: IUPAC 2016 Atomic Masses (Wang et al., Chinese Physics C 41, 030003 (2017))
All masses are in Daltons (Da), 9+ decimal places for high-mass polymer accuracy.
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------------
# Monoisotopic (single isotope) masses  [Da]
# Most abundant / lowest-mass isotope for each element
# ---------------------------------------------------------------------------
_MONOISOTOPIC_MASSES: Final[dict[str, float]] = {
    # SRS §6.3 required elements
    "H":  1.00782503207,
    "C":  12.00000000000,
    "N":  14.00307400480,
    "O":  15.99491461956,
    "S":  31.97207100000,
    "P":  30.97376163000,
    "F":  18.99840322000,
    "Cl": 34.96885268000,
    "Br": 78.91833710000,
    "I":  126.90447300000,
    "Si": 27.97692653000,
    "B":  11.00930540000,
    "Na": 22.98976928000,
    "K":  38.96370668000,
    "Li": 7.01600455000,
    "Mg": 23.98504170000,
    "Ca": 39.96259098000,
    "Zn": 63.92914201000,
}

# ---------------------------------------------------------------------------
# Isotope abundances for isotope pattern prediction (SRS §16)
# Format: { element: [(mass_Da, relative_abundance_0_to_1), ...] }
# Only major isotopes (abundance > 0.001) are included.
# ---------------------------------------------------------------------------
_ISOTOPE_DATA: Final[dict[str, list[tuple[float, float]]]] = {
    "H":  [(1.00782503207, 0.999885), (2.01410177785, 0.000115)],
    "C":  [(12.00000000000, 0.989300), (13.00335483778, 0.010700)],
    "N":  [(14.00307400480, 0.996320), (15.00010889888, 0.003680)],
    "O":  [(15.99491461956, 0.997570), (16.99913170000, 0.000380), (17.99915961000, 0.002050)],
    "S":  [(31.97207100000, 0.949900), (32.97145876000, 0.007500), (33.96786690000, 0.042500),
           (35.96708076000, 0.000100)],
    "P":  [(30.97376163000, 1.000000)],
    "F":  [(18.99840322000, 1.000000)],
    "Cl": [(34.96885268000, 0.757800), (36.96590259000, 0.242200)],
    "Br": [(78.91833710000, 0.506900), (80.91628970000, 0.493100)],
    "I":  [(126.90447300000, 1.000000)],
    "Si": [(27.97692653000, 0.922297), (28.97649470000, 0.046832), (29.97377017000, 0.030872)],
    "B":  [(10.01293695000, 0.199000), (11.00930540000, 0.801000)],
    "Na": [(22.98976928000, 1.000000)],
    "K":  [(38.96370668000, 0.932581), (39.96399848000, 0.000117), (40.96182576000, 0.067302)],
    "Li": [(6.01512289000, 0.075900), (7.01600455000, 0.924100)],
    "Mg": [(23.98504170000, 0.789900), (24.98583692000, 0.100000), (25.98259293000, 0.110100)],
    "Ca": [(39.96259098000, 0.969410), (41.95861801000, 0.006470), (42.95876668000, 0.001350),
           (43.95548156000, 0.020860), (45.95368996000, 0.000040), (47.95252290000, 0.001870)],
    "Zn": [(63.92914201000, 0.486800), (65.92603381000, 0.279500), (66.92712775000, 0.040200),
           (67.92484455000, 0.184500), (69.92531920000, 0.008000)],
}

# Electron mass for charge state calculations (SRS §11)
ELECTRON_MASS: Final[float] = 0.00054857990924

# Average masses (calculated from isotope abundances)
_AVERAGE_MASSES: Final[dict[str, float]] = {
    'H': 1.007941,
    'C': 12.010736,
    'N': 14.006743,
    'O': 15.999405,
    'S': 32.064787,
    'P': 30.973762,
    'F': 18.998403,
    'Cl': 35.452538,
    'Br': 79.903528,
    'I': 126.904473,
    'Si': 28.085413,
    'B': 10.811028,
    'Na': 22.989769,
    'K': 39.098301,
    'Li': 6.940038,
    'Mg': 24.305052,
    'Ca': 40.078023,
    'Zn': 65.329040,
}


class AtomicMassDB:
    """
    단일동위원소 질량 내장 데이터베이스.

    SRS §6.3, §6.4 준수:
    - 지원 원소: H C N O S P F Cl Br I Si B Na K Li Mg Ca Zn
    - 완전 오프라인 동작 (인터넷 불필요)
    - 재현성 보장 (하드코딩된 상수값)

    사용 예:
        mass = AtomicMassDB.get_mass("C")      # 12.0
        isotopes = AtomicMassDB.get_isotopes("Cl")  # [(34.968..., 0.7578), ...]
        all_elements = AtomicMassDB.supported_elements()
    """

    SUPPORTED_ELEMENTS: Final[frozenset[str]] = frozenset(_MONOISOTOPIC_MASSES.keys())

    @classmethod
    def get_average_mass(cls, element: str) -> float:
        """
        원소 기호로 평균 질량(Average Mass, Da)을 반환한다.

        Args:
            element: 원소 기호

        Returns:
            평균 질량
        """
        if element not in _AVERAGE_MASSES:
            raise KeyError(f"지원하지 않는 원소입니다: {element}")
        return _AVERAGE_MASSES[element]

    @classmethod
    def get_mass(cls, element: str) -> float:
        """
        원소 기호로 단일동위원소 질량(Da)을 반환한다.

        Args:
            element: 원소 기호 (대소문자 정확히 일치, 예: "C", "Cl", "Na")

        Returns:
            단일동위원소 질량 (Da)

        Raises:
            KeyError: 지원하지 않는 원소인 경우
        """
        try:
            return _MONOISOTOPIC_MASSES[element]
        except KeyError:
            supported = ", ".join(sorted(cls.SUPPORTED_ELEMENTS))
            raise KeyError(
                f"지원하지 않는 원소: '{element}'. "
                f"지원 원소 목록: {supported}"
            ) from None

    @classmethod
    def get_isotopes(cls, element: str) -> list[tuple[float, float]]:
        """
        원소의 동위원소 데이터를 반환한다.

        Args:
            element: 원소 기호

        Returns:
            [(질량_Da, 상대_풍부도), ...] 리스트.
            상대 풍부도는 0.0~1.0 범위.

        Raises:
            KeyError: 지원하지 않는 원소인 경우
        """
        if element not in _ISOTOPE_DATA:
            raise KeyError(f"동위원소 데이터 없음: '{element}'")
        return list(_ISOTOPE_DATA[element])

    @classmethod
    def supported_elements(cls) -> list[str]:
        """지원 원소 기호 목록을 알파벳 순으로 반환한다."""
        return sorted(cls.SUPPORTED_ELEMENTS)

    @classmethod
    def is_supported(cls, element: str) -> bool:
        """해당 원소가 지원되는지 확인한다."""
        return element in cls.SUPPORTED_ELEMENTS
