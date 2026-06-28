"""
MPCS — MALDI Polymer Composition Solver
Models Layer: End Group Definition
"""

from __future__ import annotations

from dataclasses import dataclass
import molmass

DEFAULT_END_GROUPS = [
    "OH/OH",
    "NH2/OH",
    "NCO/OH",
    "COOH/OH",
    "Cyclized"
]

def parse_end_group_formula(formula: str) -> float:
    if not formula or formula == "Cyclized":
        return 0.0
    mass = 0.0
    for part in formula.split('/'):
        part = part.strip()
        if not part or part.lower() == "cyclized":
            continue
        try:
            mass += molmass.Formula(part).isotope.mass
        except Exception:
            pass
    return mass

def parse_end_group_average_mass(formula: str) -> float:
    if not formula or formula == "Cyclized":
        return 0.0
    mass = 0.0
    for part in formula.split('/'):
        part = part.strip()
        if not part or part.lower() == "cyclized":
            continue
        try:
            mass += molmass.Formula(part).mass
        except Exception:
            pass
    return mass

@dataclass
class EndGroup:
    """
    고분자 말단기 정의.
    """
    formula: str = "OH/OH"
    is_custom_mass: bool = False
    custom_mass: float = 0.0

    @property
    def mass(self) -> float:
        if self.is_custom_mass:
            return self.custom_mass
        return parse_end_group_formula(self.formula)

    @property
    def average_mass(self) -> float:
        if self.is_custom_mass:
            return self.custom_mass
        return parse_end_group_average_mass(self.formula)

    @classmethod
    def from_dict(cls, data: dict) -> EndGroup:
        # backward compatibility: if preset exists, use it
        if "preset" in data:
            preset = data["preset"]
            if preset == "Custom":
                return cls(is_custom_mass=True, custom_mass=data.get("custom_mass", 0.0))
            else:
                return cls(formula=preset, is_custom_mass=False)
        return cls(
            formula=data.get("formula", "OH/OH"),
            is_custom_mass=data.get("is_custom_mass", False),
            custom_mass=data.get("custom_mass", 0.0)
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.is_custom_mass and self.custom_mass <= 0.0:
            errors.append(
                "사용자 정의 말단기의 질량이 0 이하입니다. "
                "양수 질량(Da)을 입력하십시오."
            )
        return errors

    def __str__(self) -> str:
        if self.is_custom_mass:
            return f"Custom ({self.custom_mass:.6f} Da)"
        return f"{self.formula} ({self.mass:.6f} Da)"
