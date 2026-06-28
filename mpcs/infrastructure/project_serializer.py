"""
MPCS — MALDI Polymer Composition Solver
Infrastructure Layer: Project Serializer

Q12 사용자 확인:
    - 현재 설정한 모든 것을 .mpcs 파일(JSON)로 저장/불러오기
    - 처음 실행 시 기존 프로젝트를 열 수 있도록 표시
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mpcs.models.adduct import Adduct
from mpcs.models.constraint import Constraint
from mpcs.models.end_group import EndGroup
from mpcs.models.feed_ratio import FeedRatio, FeedRatioEntry
from mpcs.models.monomer import Monomer, MonomerType
from mpcs.models.project import Project
from mpcs.models.result import PeakData, SECData


# 프로젝트 파일 확장자
PROJECT_FILE_EXTENSION = ".mpcs"
# 현재 직렬화 스키마 버전
SCHEMA_VERSION = "1.0"


class ProjectSerializeError(IOError):
    """프로젝트 저장 오류."""


class ProjectDeserializeError(IOError):
    """프로젝트 불러오기 오류."""


class ProjectSerializer:
    """
    MPCS 프로젝트를 JSON(.mpcs) 파일로 직렬화/역직렬화한다.

    Q12: 현재 설정한 모든 것을 저장하고 불러올 수 있어야 한다.
    저장 항목: 모노머, 제약식, 말단기, 어덕트, 공급비, 피크 데이터, SEC 데이터,
               Average Block Mode 설정, 프로젝트 이름, 생성/수정 시각

    사용 예:
        serializer = ProjectSerializer()
        serializer.save(project, "my_project.mpcs")
        loaded = serializer.load("my_project.mpcs")
    """

    def save(self, project: Project, filepath: str | Path) -> None:
        """
        프로젝트를 JSON 파일로 저장한다.

        Args:
            project:  저장할 프로젝트
            filepath: 저장 경로 (.mpcs 확장자 권장)

        Raises:
            ProjectSerializeError: 저장 실패
        """
        path = Path(filepath)
        try:
            data = self._serialize(project)
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            path.write_text(json_str, encoding="utf-8")
        except Exception as exc:
            raise ProjectSerializeError(
                f"프로젝트 저장 실패 '{filepath}': {exc}"
            ) from exc

    def load(self, filepath: str | Path) -> Project:
        """
        JSON 파일에서 프로젝트를 불러온다.

        Args:
            filepath: 불러올 파일 경로

        Returns:
            Project 인스턴스

        Raises:
            ProjectDeserializeError: 불러오기 실패
        """
        path = Path(filepath)
        if not path.exists():
            raise ProjectDeserializeError(
                f"파일이 존재하지 않습니다: '{filepath}'"
            )

        try:
            json_str = path.read_text(encoding="utf-8")
            data = json.loads(json_str)
            return self._deserialize(data, str(filepath))
        except ProjectDeserializeError:
            raise
        except Exception as exc:
            raise ProjectDeserializeError(
                f"프로젝트 불러오기 실패 '{filepath}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize(self, project: Project) -> dict[str, Any]:
        """Project 객체를 직렬화 가능한 딕셔너리로 변환한다."""
        project.touch()  # 저장 시 수정 시각 갱신
        return {
            "schema_version": SCHEMA_VERSION,
            "name": project.name,
            "created_at": project.created_at,
            "modified_at": project.modified_at,
            "average_block_mode": project.average_block_mode,
            "monomers": [self._serialize_monomer(m) for m in project.monomers],
            "constraints": [self._serialize_constraint(c) for c in project.constraints],
            "end_group": self._serialize_end_group(project.end_group),
            "adducts": [self._serialize_adduct(a) for a in project.adducts],
            "feed_ratio": self._serialize_feed_ratio(project.feed_ratio),
            "peak_data": self._serialize_peak_data(project.peak_data),
            "sec_data": self._serialize_sec_data(project.sec_data),
        }

    @staticmethod
    def _serialize_monomer(m: Monomer) -> dict[str, Any]:
        return {
            "name": m.name,
            "monomer_type": m.monomer_type.value,
            "formula": m.formula,
            "exact_mass": m.exact_mass,
            "min_count": m.min_count,
            "max_count": m.max_count,
            "sub_items": [
                {
                    "name": s.name,
                    "sub_type": s.sub_type.value,
                    "formula_or_mass": s.formula_or_mass,
                    "exact_mass": s.exact_mass,
                    "count_min": s.count_min,
                    "count_max": s.count_max,
                }
                for s in (m.sub_items or [])
            ],
        }

    @staticmethod
    def _serialize_constraint(c: Constraint) -> dict[str, Any]:
        return {
            "expression": c.expression,
            "is_active": c.is_active,
        }

    @staticmethod
    def _serialize_end_group(eg: EndGroup) -> dict[str, Any]:
        return {
            "preset": eg.preset.value,
            "custom_mass": eg.custom_mass,
        }

    @staticmethod
    def _serialize_adduct(a: Adduct) -> dict[str, Any]:
        return {
            "label": a.label,
            "adduct_mass": a.adduct_mass,
            "adduct_average_mass": a.adduct_average_mass,
            "charge": a.charge,
            "enabled": a.enabled,
        }

    @staticmethod
    def _serialize_feed_ratio(fr: FeedRatio) -> dict[str, Any]:
        return {
            "entries": [
                {"component_name": e.component_name, "mmol": e.mmol}
                for e in fr.entries
            ],
            "tolerance_pct": fr.tolerance_pct,
        }

    @staticmethod
    def _serialize_peak_data(pd: PeakData) -> dict[str, Any]:
        return {
            "mz_values": pd.mz_values,
            "intensities": pd.intensities,
        }

    @staticmethod
    def _serialize_sec_data(sd: SECData | None) -> dict[str, Any] | None:
        if sd is None:
            return None
        return {"mn": sd.mn, "mw": sd.mw, "pdi": sd.pdi}

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    def _deserialize(self, data: dict[str, Any], filepath: str) -> Project:
        """딕셔너리에서 Project 객체를 복원한다."""
        # 스키마 버전 확인
        version = data.get("schema_version", "unknown")
        if version != SCHEMA_VERSION:
            # 향후 마이그레이션 로직 추가 지점
            pass  # 현재는 경고 없이 진행

        try:
            monomers = [self._deserialize_monomer(m) for m in data.get("monomers", [])]
            constraints = [self._deserialize_constraint(c) for c in data.get("constraints", [])]
            end_group = self._deserialize_end_group(data.get("end_group", {}))
            adducts = [self._deserialize_adduct(a) for a in data.get("adducts", [])]
            feed_ratio = self._deserialize_feed_ratio(data.get("feed_ratio", {}))
            peak_data = self._deserialize_peak_data(data.get("peak_data", {}))
            sec_data = self._deserialize_sec_data(data.get("sec_data"))

            return Project(
                name=data.get("name", "불러온 프로젝트"),
                monomers=monomers,
                constraints=constraints,
                end_group=end_group,
                adducts=adducts,
                feed_ratio=feed_ratio,
                peak_data=peak_data,
                sec_data=sec_data,
                average_block_mode=data.get("average_block_mode", False),
                created_at=data.get("created_at", datetime.now().isoformat()),
                modified_at=data.get("modified_at", datetime.now().isoformat()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectDeserializeError(
                f"'{filepath}' 파일 구조 오류: {exc}"
            ) from exc

    @staticmethod
    def _deserialize_monomer(data: dict[str, Any]) -> Monomer:
        from mpcs.models.monomer import BlockSubItem
        sub_items = []
        for s in data.get("sub_items", []):
            sub_items.append(
                BlockSubItem(
                    name=s["name"],
                    sub_type=MonomerType(s["sub_type"]),
                    formula_or_mass=s["formula_or_mass"],
                    exact_mass=float(s["exact_mass"]),
                    count_min=int(s["count_min"]),
                    count_max=int(s["count_max"]),
                )
            )
        return Monomer(
            name=data["name"],
            monomer_type=MonomerType(data["monomer_type"]),
            formula=data["formula"],
            exact_mass=float(data["exact_mass"]),
            min_count=int(data["min_count"]),
            max_count=int(data["max_count"]),
            sub_items=sub_items,
        )


    @staticmethod
    def _deserialize_constraint(data: dict[str, Any]) -> Constraint:
        return Constraint(
            expression=data["expression"],
            is_active=bool(data.get("is_active", True)),
        )

    @staticmethod
    def _deserialize_end_group(data: dict[str, Any]) -> EndGroup:
        preset_str = data.get("preset", "OH/OH")
        # preset 값으로 Enum 역변환
        preset = next(
            (p for p in EndGroupPreset if p.value == preset_str),
            EndGroupPreset.OH_OH,
        )
        return EndGroup(
            preset=preset,
            custom_mass=float(data.get("custom_mass", 0.0)),
            custom_average_mass=float(data.get("custom_average_mass", data.get("custom_mass", 0.0))),
        )

    @staticmethod
    def _deserialize_adduct(data: dict[str, Any]) -> Adduct:
        return Adduct(
            label=data["label"],
            adduct_mass=float(data["adduct_mass"]),
            adduct_average_mass=float(data.get("adduct_average_mass", data["adduct_mass"])),
            charge=int(data["charge"]),
            enabled=bool(data.get("enabled", False)),
        )

    @staticmethod
    def _deserialize_feed_ratio(data: dict[str, Any]) -> FeedRatio:
        entries = [
            FeedRatioEntry(
                component_name=e["component_name"],
                mmol=float(e["mmol"]),
            )
            for e in data.get("entries", [])
        ]
        return FeedRatio(
            entries=entries,
            tolerance_pct=float(data.get("tolerance_pct", 20.0)),
        )

    @staticmethod
    def _deserialize_peak_data(data: dict[str, Any]) -> PeakData:
        return PeakData(
            mz_values=[float(v) for v in data.get("mz_values", [])],
            intensities=[float(v) for v in data.get("intensities", [])],
        )

    @staticmethod
    def _deserialize_sec_data(data: dict[str, Any] | None) -> SECData | None:
        if data is None:
            return None
        return SECData(
            mn=float(data["mn"]),
            mw=float(data["mw"]),
            pdi=float(data["pdi"]),
        )
