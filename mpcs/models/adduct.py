from __future__ import annotations

from dataclasses import dataclass
import re
import molmass


# ---------------------------------------------------------------------------
# 어덕트 파서
# ---------------------------------------------------------------------------

def parse_adduct_label(label: str) -> tuple[float, float, int]:
    """
    '[M+2Na]2+' 또는 '[M-H]-' 형식의 어덕트 문자열을 파싱하여 (정밀질량, 평균질량, 전하) 반환.
    """
    label = label.strip()
    if not label:
        raise ValueError("어덕트 문자열이 비어 있습니다.")
        
    m = re.match(r'^\[M([+-].*?)\](\d*)([+-])?$', label)
    if not m:
        raise ValueError(f"지원되지 않는 어덕트 형식입니다 (예: [M+Na]+): {label}")
        
    formula_str = m.group(1)
    z_str = m.group(2)
    sign_str = m.group(3)
    
    charge_val = int(z_str) if z_str else 1
    if sign_str == "-":
        charge_val = -charge_val
    elif not sign_str:
        charge_val = 1
        
    if charge_val == 0:
        raise ValueError("전하(z)는 0이 될 수 없습니다.")
        
    parts = re.findall(r'([+-])([^+-]+)', formula_str)
    
    exact_mass = 0.0
    avg_mass = 0.0
    for sign, part_formula in parts:
        part_formula = part_formula.strip()
        
        # '2Na' -> '(Na)2'
        m_num = re.match(r'^(\d+)(.+)$', part_formula)
        if m_num:
            part_formula = f"({m_num.group(2)}){m_num.group(1)}"
            
        try:
            f = molmass.Formula(part_formula)
            if sign == '+':
                exact_mass += f.isotope.mass
                avg_mass += f.mass
            else:
                exact_mass -= f.isotope.mass
                avg_mass -= f.mass
        except Exception:
            raise ValueError(f"올바르지 않은 분자식입니다: {part_formula}")
            
    return exact_mass, avg_mass, abs(charge_val)


@dataclass
class Adduct:
    """
    MALDI 이온화 어덕트 정의.
    """
    label: str
    adduct_mass: float = 0.0
    charge: int = 1
    adduct_average_mass: float = 0.0
    enabled: bool = False

    def __post_init__(self):
        # 질량과 전하가 0이면 파싱하여 자동 계산 (새로 생성될 때)
        if self.adduct_mass == 0.0 or self.charge == 0:
            self.recalculate()
            
    def recalculate(self):
        exact, avg, z = parse_adduct_label(self.label)
        self.adduct_mass = exact
        self.adduct_average_mass = avg
        self.charge = z

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    def calc_mz(self, neutral_mw: float) -> float:
        return (neutral_mw + self.adduct_mass) / self.charge

    def calc_mz_average(self, neutral_mw: float) -> float:
        return (neutral_mw + self.adduct_average_mass) / self.charge

    def calc_neutral_mw(self, mz: float) -> float:
        return mz * self.charge - self.adduct_mass

    def calc_neutral_mw_average(self, mz: float) -> float:
        return mz * self.charge - self.adduct_average_mass

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.label or not self.label.strip():
            errors.append("어덕트 레이블이 비어 있습니다")
        if self.charge <= 0:
            errors.append(f"전하 수가 0 이하입니다: {self.charge}")
        try:
            parse_adduct_label(self.label)
        except ValueError as e:
            errors.append(str(e))
        return errors

    def __str__(self) -> str:
        status = "✓" if self.enabled else "○"
        return f"{status} {self.label}  adduct={self.adduct_mass:.6f} Da  z={self.charge}"


# ---------------------------------------------------------------------------
# 프리셋 어덕트 목록 (UI 초기값)
# ---------------------------------------------------------------------------

def make_default_adducts() -> list[Adduct]:
    """초기 어덕트 목록을 생성한다."""
    return [
        Adduct("[M+H]+", enabled=False),
        Adduct("[M+Na]+", enabled=True),
        Adduct("[M+K]+", enabled=False),
        Adduct("[M+NH4]+", enabled=False),
        Adduct("[M+2Na]2+", enabled=False),
        Adduct("[M+3Na]3+", enabled=False),
    ]