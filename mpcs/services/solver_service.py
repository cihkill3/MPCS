"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Solver Service (Exhaustive Search)

SRS §13 Solver Engine:
    §13.1 Search Mode: Exhaustive Search (전수탐색)
    §13.2 Workflow:
        1. 후보 조성 생성
        2. 제약식 적용
        3. 공급비 필터 적용
        4. 이론 질량 계산
        5. 관측 질량과 비교
        6. 오차 계산
        7. 후보 순위 결정
    §13.3 Error = ABS(Mobserved - Mcalculated)
    §13.4 Ranking: minimum error 기준 오름차순

SRS §21 Performance:
    단일 피크 < 1초
    100 피크 < 10초

최적화 전략:
    1. 제약식으로 결정되는 종속 변수는 루프에서 제외 (탐색 공간 축소)
    2. 상한 질량 조기 컷 (누적 질량이 이미 한계 초과 시 branch 제거)
    3. NumPy 배열 연산으로 질량 계산 벡터화
    4. lru_cache로 동일 조성 재계산 방지
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Iterator

import numpy as np

from mpcs.core.mass_calculator import MassCalculator
from mpcs.models.adduct import Adduct
from mpcs.models.constraint import Constraint
from mpcs.models.end_group import EndGroup
from mpcs.models.feed_ratio import FeedRatio
from mpcs.models.monomer import Monomer, MonomerType
from mpcs.models.result import (
    Composition,
    MAX_RESULTS,
    RankedResultSet,
    SECData,
    SolverResult,
)
from mpcs.services.constraint_engine import (
    ConstraintEngine,
    ParsedConstraint,
)


@dataclass
class SolverParams:
    """
    솔버 실행 파라미터.

    Attributes:
        peak_mz:       관측 m/z 값 (Da)
        monomers:      모노머 목록 (SRS §5)
        constraints:   제약식 목록 (SRS §8)
        feed_ratio:    공급비 (SRS §9). None이면 필터 비활성
        end_group:     말단기 (SRS §10)
        adducts:       활성화된 어덕트 목록 (SRS §11)
        sec_data:      SEC 데이터 (SRS §17). None이면 필터 비활성
        tolerance_da:  질량 허용 오차 (Da). SRS §21 참조.
    """

    peak_mz: float
    monomers: list[Monomer]
    constraints: list[Constraint]
    end_group: EndGroup
    adducts: list[Adduct]
    feed_ratio: FeedRatio | None = None
    sec_data: SECData | None = None
    tolerance_da: float = 0.05
    mass_type: str = "EXACT"  # "EXACT" or "AVERAGE"
    isotope_offset_count: int = 0

    def validate(self) -> list[str]:
        """파라미터 유효성 검사."""
        errors: list[str] = []
        if self.peak_mz <= 0.0:
            errors.append(f"m/z 값이 0 이하입니다: {self.peak_mz}")
        if not self.monomers:
            errors.append("모노머가 없습니다")
        if not self.adducts:
            errors.append("활성화된 어덕트가 없습니다")
        if self.tolerance_da < 0.0:
            errors.append(f"허용 오차가 음수입니다: {self.tolerance_da}")
        return errors


class SolverService:
    """
    MALDI 피크 단일동위원소 정밀질량 역산 솔버.

    SRS §13 Solver Engine 완전 구현 (Exhaustive Search).

    사용 예:
        engine = ConstraintEngine()
        calc = MassCalculator()
        solver = SolverService(calc, engine)

        params = SolverParams(
            peak_mz=15123.43,
            monomers=[...],
            constraints=[Constraint("HDI = PLA + SMA - 1")],
            end_group=EndGroup(),
            adducts=[enabled_adduct],
        )
        result_set = solver.solve(params)
        print(result_set.best())
    """

    def __init__(
        self,
        mass_calculator: MassCalculator,
        constraint_engine: ConstraintEngine,
    ) -> None:
        self._calc = mass_calculator
        self._engine = constraint_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        params: SolverParams,
        progress_callback: Callable[[int, int, int], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> RankedResultSet:
        """
        단일 m/z 피크에 대해 전수탐색 솔버를 실행한다.

        SRS §13.2 Workflow 완전 구현.

        Args:
            params:            솔버 파라미터
            progress_callback: (현재_후보_수, 전체_후보_수) 콜백.
                               호출 빈도는 내부적으로 제한됨.
            cancel_flag:       True 반환 시 즉시 중단.

        Returns:
            RankedResultSet (error_da 기준 오름차순)

        Raises:
            ValueError: 파라미터 유효성 검사 실패
        """
        # 파라미터 검증
        param_errors = params.validate()
        if param_errors:
            raise ValueError(f"솔버 파라미터 오류: {'; '.join(param_errors)}")

        # Step 1: 제약식 파싱 및 위상 정렬
        monomer_names = []
        block_names = set()
        mass_map: dict[str, float] = {}

        for m in params.monomers:
            monomer_names.append(m.name)
            mass_map[m.name] = m.effective_average_mass() if params.mass_type == "AVERAGE" else m.effective_mass()
            if m.monomer_type == MonomerType.BLOCK and m.sub_items:
                block_names.add(m.name)
                for sub in m.sub_items:
                    monomer_names.append(sub.name)
                    mass_map[sub.name] = sub.average_mass if params.mass_type == "AVERAGE" else sub.exact_mass

        # 말단기: EndGroup.mw 로 참조 가능 (이름 'EndGroup')
        mass_map["EndGroup"] = params.end_group.average_mass if params.mass_type == "AVERAGE" else params.end_group.mass
        # 어덕트: 어덕트 레이블로도 참조 가능
        for adduct in params.adducts:
            if adduct.label not in mass_map:
                mass_map[adduct.label] = adduct.adduct_average_mass if params.mass_type == "AVERAGE" else adduct.adduct_mass

        parsed_constraints = self._engine.parse_all(
            params.constraints, monomer_names, mass_map
        )
        sorted_constraints = self._engine.topological_sort(parsed_constraints)

        # 종속 변수 식별 (등식 제약식의 LHS)
        # 이 변수들은 탐색 루프에서 제외하고 제약식으로 값을 결정한다
        dependent_vars: set[str] = {
            pc.equality_lhs
            for pc in sorted_constraints
            if pc.equality_lhs is not None
        }

        # 독립 변수 모노머 (탐색 루프 대상)
        free_monomers = [m for m in params.monomers if m.name not in dependent_vars]
        # 종속 변수 모노머
        dep_monomers = {m.name: m for m in params.monomers if m.name in dependent_vars}

        # 말단기 질량
        end_group_mass = params.end_group.average_mass if params.mass_type == "AVERAGE" else params.end_group.mass

        # 각 어덕트별로 중성 MW 목표값 계산
        # 어덕트별로 역산된 중성 MW를 허용 범위로 변환
        target_mw_ranges: list[tuple[float, float, Adduct]] = []
        for adduct in params.adducts:
            neutral_mw = adduct.calc_neutral_mw(params.peak_mz)
            target_mw_ranges.append((
                neutral_mw - params.tolerance_da,
                neutral_mw + params.tolerance_da,
                adduct,
            ))

        # 탐색 범위 (독립 변수만)
        ranges = []
        for m in free_monomers:
            if m.monomer_type == MonomerType.BLOCK and m.sub_items:
                block_states = []
                for b_cnt in m.search_range():
                    if b_cnt == 0:
                        state = {m.name: 0}
                        for sub in m.sub_items:
                            state[sub.name] = 0
                        block_states.append(state)
                    else:
                        sub_ranges = []
                        for sub in m.sub_items:
                            if sub.name in dependent_vars:
                                sub_ranges.append([0])
                            else:
                                sub_ranges.append(range(b_cnt * sub.count_min, b_cnt * sub.count_max + 1))
                        
                        for sub_counts in itertools.product(*sub_ranges):
                            state = {m.name: b_cnt}
                            for sub, cnt in zip(m.sub_items, sub_counts):
                                state[sub.name] = cnt
                            block_states.append(state)
                ranges.append(block_states)
            else:
                ranges.append([{m.name: cnt} for cnt in m.search_range()])

        total_candidates = 1
        for r in ranges:
            total_candidates *= len(r)

        # 결과 수집
        results: list[SolverResult] = []
        processed = 0
        _PROGRESS_INTERVAL = max(1, total_candidates // 1000)

        for candidate_counts in itertools.product(*ranges):
            # 취소 확인
            if cancel_flag is not None and cancel_flag():
                break

            # 진행률 콜백
            processed += 1
            if progress_callback is not None and processed % _PROGRESS_INTERVAL == 0:
                progress_callback(processed, len(results), total_candidates)

            # 현재 독립 변수 값 딕셔너리
            import collections
            current_values: dict[str, int] = collections.defaultdict(int)
            for state in candidate_counts:
                for k, v in state.items():
                    current_values[k] += v

            # Step 2: 제약식으로 종속 변수 결정 + 검증
            constraint_valid = True
            for pc in sorted_constraints:
                if pc.equality_lhs is not None and pc.equality_lhs in dependent_vars:
                    # 종속 변수 값 결정
                    resolved = self._engine.resolve(pc, current_values)
                    if resolved is None:
                        constraint_valid = False
                        break
                    current_values[pc.equality_lhs] = resolved
                else:
                    # 불등식 또는 복합 등식 → 검증
                    try:
                        if not self._engine.evaluate(pc, current_values):
                            constraint_valid = False
                            break
                    except Exception:
                        constraint_valid = False
                        break

            if not constraint_valid:
                continue

            # 종속 변수의 min/max 범위 검증
            for dep_name, dep_monomer in dep_monomers.items():
                val = current_values.get(dep_name, -1)
                if val < dep_monomer.min_count or val > dep_monomer.max_count:
                    constraint_valid = False
                    break

            if constraint_valid:
                # Block 하위 성분 동적 범위 검증 (종속 변수일 경우를 대비)
                for m in params.monomers:
                    if m.monomer_type == MonomerType.BLOCK and m.sub_items:
                        b_cnt = current_values.get(m.name, 0)
                        for sub in m.sub_items:
                            sub_cnt = current_values.get(sub.name, 0)
                            if sub_cnt < b_cnt * sub.count_min or sub_cnt > b_cnt * sub.count_max:
                                constraint_valid = False
                                break
                    if not constraint_valid:
                        break

            if not constraint_valid:
                continue

            # Step 3: 공급비 필터 (SRS §13.2 step 3)
            if params.feed_ratio is not None:
                if not params.feed_ratio.check_composition(current_values):
                    continue

            # Step 4: 이론 질량 계산
            neutral_mw = self._calc_composition_mass(
                current_values, mass_map, block_names, end_group_mass
            )

            # SEC 필터 (SRS §17)
            if params.sec_data is not None:
                if not params.sec_data.contains(neutral_mw):
                    continue

            # Step 5-7: 각 어덕트별 오차 계산 및 범위 내 결과 수집
            for adduct in params.adducts:
                if params.mass_type == "AVERAGE":
                    theoretical_mz = adduct.calc_mz_average(neutral_mw)
                else:
                    theoretical_mz = adduct.calc_mz(neutral_mw)

                for n in range(params.isotope_offset_count + 1):
                    offset = 1.00335 * n / adduct.charge
                    matched_mz = theoretical_mz + offset
                    error_da = abs(params.peak_mz - matched_mz)

                    if error_da <= params.tolerance_da:
                        composition = Composition(dict(current_values))
                        # 전체 이온 분자식 계산 (직접 입력 질량 포함 시 None)
                        ion_formula = self._build_ion_formula(
                            current_values, params.monomers,
                            params.end_group, adduct
                        )
                        result = SolverResult(
                            composition=composition,
                            calculated_mass=theoretical_mz,
                            observed_mass=params.peak_mz,
                            error_da=error_da,
                            adduct_label=adduct.label,
                            isotope_offset=n,
                            formula=ion_formula,
                        )
                        results.append(result)

        # 최종 진행률
        if progress_callback is not None:
            progress_callback(processed, len(results), total_candidates)

        # Step 7: 오차 기준 정렬 (SRS §13.4) + Q8: 상위 MAX_RESULTS(100)개만 반환
        results.sort(key=lambda r: r.error_da)
        results = results[:MAX_RESULTS]

        return RankedResultSet(peak_mz=params.peak_mz, results=results)

    def solve_multi_peak(
        self,
        peak_mz_list: list[float],
        base_params: SolverParams,
        progress_callback: Callable[[int, int, int], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> list[RankedResultSet]:
        """
        다중 피크에 대해 순차적으로 솔버를 실행한다.

        SRS §21: 100 피크 < 10초 목표.

        Args:
            peak_mz_list:      m/z 값 목록
            base_params:       기본 솔버 파라미터 (peak_mz는 무시됨)
            progress_callback: (현재_피크, 전체_피크) 콜백
            cancel_flag:       True 반환 시 즉시 중단

        Returns:
            RankedResultSet 리스트 (입력 피크 순서와 동일)
        """
        results: list[RankedResultSet] = []
        total = len(peak_mz_list)

        for i, mz in enumerate(peak_mz_list):
            if cancel_flag is not None and cancel_flag():
                break

            # 각 피크에 대해 별도 SolverParams 생성
            import dataclasses
            peak_params = dataclasses.replace(base_params, peak_mz=mz)
            result_set = self.solve(peak_params, cancel_flag=cancel_flag)
            results.append(result_set)

            if progress_callback is not None:
                progress_callback(i + 1, total)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------



    def _build_ion_formula(
        self,
        values: dict[str, int],
        monomers: list[Monomer],
        end_group,
        adduct: "Adduct",
    ) -> str | None:
        """
        조성(current_values) + 말단기 + 어덕트를 합산한 이온 분자식 문자열을 반환한다.

        current_values는 플래튼된 구조:
            - 일반 모노머/Crosslinker: {monomer_name: count}
            - BLOCK: {block_name: block_count, sub_item_name: total_sub_count, ...}

        직접 질량 입력이 포함된 경우 None 반환.
        """
        from mpcs.core.formula_parser import FormulaParser
        parser = FormulaParser()

        # ── 1. 원본 monomers에서 이름 → formula 매핑 구축 ──────────────────────
        # (a) 일반 모노머/Crosslinker: name → formula 문자열
        # (b) BLOCK: block_name → ("BLOCK", sub_items)
        # (c) sub-item: sub_name → formula 문자열  (블록 외부에서 직접 참조되는 경우)
        #
        # values 키는 일반 모노머 이름 또는 블록 이름 또는 sub-item 이름(플래튼)이다.
        # 블록 이름이 values에 있으면 블록 반복 횟수로 처리하지만,
        # 실제 원소 기여는 sub-item 이름별 count에서 산출된다.
        # 따라서 블록 이름 자체는 원소 기여 없이 스킵하면 됨.

        # 일반 모노머 formula 맵
        normal_formula_map: dict[str, str | None] = {}
        # sub-item formula 맵: sub_name → formula (None = 직접 질량)
        sub_item_formula_map: dict[str, str | None] = {}
        # 블록 이름 집합 (values에서 스킵할 키)
        block_names: set[str] = set()

        for m in monomers:
            if m.monomer_type == MonomerType.BLOCK:
                block_names.add(m.name)
                # sub-item 각각의 formula 등록
                for sub in m.sub_items:
                    f = sub.formula_or_mass
                    if f.startswith("~") or _is_numeric(f):
                        sub_item_formula_map[sub.name] = None  # 직접 질량
                    else:
                        sub_item_formula_map[sub.name] = f
            else:
                f = m.formula
                if f.startswith("~"):
                    normal_formula_map[m.name] = None
                else:
                    normal_formula_map[m.name] = f

        # ── 2. 원소 누적 ─────────────────────────────────────────────────────────
        total_elements: dict[str, int] = {}

        def _add_elements(elements: dict[str, int], multiplier: int = 1) -> None:
            for elem, cnt in elements.items():
                total_elements[elem] = total_elements.get(elem, 0) + cnt * multiplier

        for name, count in values.items():
            if count <= 0:
                continue

            # 블록 이름: 원소 기여 없음 (sub-item 카운트가 따로 values에 있음)
            if name in block_names:
                continue

            # sub-item으로 등록된 경우
            if name in sub_item_formula_map:
                f = sub_item_formula_map[name]
                if f is None:
                    return None  # 직접 질량 입력 포함
                try:
                    elems = parser.parse(f)
                    _add_elements(elems, count)
                except Exception:
                    return None
                continue

            # 일반 모노머로 등록된 경우
            if name in normal_formula_map:
                f = normal_formula_map[name]
                if f is None:
                    return None  # 직접 질량 입력 포함
                try:
                    elems = parser.parse(f)
                    _add_elements(elems, count)
                except Exception:
                    return None
                continue

            # 어디에도 없는 이름: 분자식 알 수 없음 → None
            return None

        # ── 3. 말단기 기여 ───────────────────────────────────────────────────────
        if end_group.is_custom_mass:
            return None
            
        eg_elems = {}
        for part in end_group.formula.split('/'):
            part = part.strip()
            if not part or part.lower() == 'cyclized':
                continue
            try:
                part_elems = parser.parse(part)
                for el, c in part_elems.items():
                    eg_elems[el] = eg_elems.get(el, 0) + c
            except Exception:
                return None
        _add_elements(eg_elems)

        # ── 4. 어덕트 기여 ───────────────────────────────────────────────────────
        import re
        adduct_elems = {}
        label = adduct.label.strip()
        m = re.match(r'^\[M([+-].*?)\](\d*)([+-])?$', label)
        if m:
            formula_str = m.group(1)
            parts = re.findall(r'([+-])([^+-]+)', formula_str)
            for sign, part_formula in parts:
                part_formula = part_formula.strip()
                m_num = re.match(r'^(\d+)(.+)$', part_formula)
                if m_num:
                    part_formula = f"({m_num.group(2)}){m_num.group(1)}"
                try:
                    part_elems = parser.parse(part_formula)
                    for el, c in part_elems.items():
                        if sign == '+':
                            adduct_elems[el] = adduct_elems.get(el, 0) + c
                        else:
                            adduct_elems[el] = adduct_elems.get(el, 0) - c
                except Exception:
                    return None
        _add_elements(adduct_elems)

        # ── 5. 원소 → Hill 순서 분자식 ──────────────────────────────────────────
        return _elements_to_formula(total_elements)

    def _calc_composition_mass(
        self,
        values: dict[str, int],
        mass_map: dict[str, float],
        block_names: set[str],
        end_group_mass: float,
    ) -> float:
        """
        조성의 중성 분자량을 계산한다.

        MW = Σ(n_i × ExactMass_i) + EndGroupMass

        Block 이름은 무시하고 하위 성분(sub_items)의 질량을 더한다.
        """
        total = end_group_mass
        for name, count in values.items():
            if count > 0 and name not in block_names and name in mass_map:
                total += count * mass_map[name]

        return total


def _is_numeric(text: str) -> bool:
    """문자열이 순수 숫자인지 확인한다."""
    try:
        float(text)
        return True
    except ValueError:
        return False


def _elements_to_formula(elements: dict[str, int]) -> str:
    """원소 카운트 딕셔너리를 Hill 순서 분자식 문자열로 변환한다."""
    parts = []
    # Hill 순서: C 먼저, H 다음, 나머지 알파벳 순
    order = []
    if "C" in elements:
        order.append("C")
    if "H" in elements:
        order.append("H")
    for elem in sorted(elements):
        if elem not in ("C", "H"):
            order.append(elem)
    for elem in order:
        cnt = elements.get(elem, 0)
        if cnt > 0:
            parts.append(f"{elem}{cnt}" if cnt > 1 else elem)
    return "".join(parts)
