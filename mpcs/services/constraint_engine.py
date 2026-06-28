"""
MPCS — MALDI Polymer Composition Solver
Services Layer: Constraint Engine

SRS §8 Constraint Module:
    §8.2 지원 표현식: HDI = PLA + SMA - 1, EO = 45 * PLA
    §8.3 지원 연산자: + - * / ^ ( )
    §8.4 지원 비교: = < <= > >=
    §8.5 지원 함수: ABS() ROUND() INT()

변수 의미:
    name     — 해당 성분의 반복 횟수 (정수, ≥ 0)
    name.mw  — 해당 성분 1개의 정밀질량 (실수 상수, Da)
               사용 가능한 성분: 모노머, Block, 말단기, 어덕트

    예시:
        HDI = PLA + SMA - 1          # 반복 횟수 제약
        MW_total = EO * EO.mw + LA * LA.mw + EndGroup.mw
        EO * EO.mw >= 1000           # 특정 성분의 질량 조건

구현 방식:
    - SymPy를 사용하여 제약식을 심볼릭으로 파싱·평가한다.
    - name.mw는 파싱 전처리 단계에서 숫자 상수로 치환된다.
      (예: EO.mw → 44.026214)
    - 좌변(LHS) 변수를 우변(RHS) 수식으로 표현하여
      종속 변수를 솔버 탐색 루프에서 제외한다 (탐색 공간 축소).
    - 다중 제약식은 토폴로지 정렬로 평가 순서를 결정한다.
    - 순환 의존성은 오류로 처리한다.

⚠️ ASSUMPTION (Q3):
    제약식 우변 계산 결과가 비정수인 경우 해당 후보를 제거한다.

⚠️ ASSUMPTION (Q6):
    순환 의존성(A = f(B), B = f(A)) 발생 시 ConstraintParseError 발생.
    평가 순서는 의존 그래프의 위상 정렬(Kahn's algorithm) 사용.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterator

import sympy
from sympy import Symbol, sympify, Integer, Float, lambdify
from sympy.core.expr import Expr

from mpcs.models.constraint import Constraint


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ConstraintParseError(ValueError):
    """제약식 파싱 오류."""

    def __init__(self, expression: str, reason: str) -> None:
        self.expression = expression
        self.reason = reason
        super().__init__(f"제약식 파싱 오류 '{expression}': {reason}")


class ConstraintEvalError(RuntimeError):
    """제약식 평가 오류."""

    def __init__(self, expression: str, reason: str) -> None:
        self.expression = expression
        self.reason = reason
        super().__init__(f"제약식 평가 오류 '{expression}': {reason}")


class CircularDependencyError(ConstraintParseError):
    """순환 의존성 오류 (Q6)."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(
            "순환 참조",
            f"제약식 간 순환 의존성 발견: {' → '.join(cycle)}"
        )


# ---------------------------------------------------------------------------
# Parsed constraint (internal representation)
# ---------------------------------------------------------------------------

@dataclass
class ParsedConstraint:
    """
    파싱된 제약식의 내부 표현.

    equality_lhs:  등식 형태인 경우 좌변 변수명 (예: "HDI")
                   비등식이거나 좌변이 단순 변수가 아닌 경우 None
    lhs_expr:      SymPy 좌변 표현식
    rhs_expr:      SymPy 우변 표현식
    comparison:    비교 연산자 ("=", "<", "<=", ">", ">=")
    original:      원본 제약식 문자열
    free_vars:     우변에 포함된 변수 이름 집합 (name.mw 제외, 반복횟수 변수만)
    """

    original: str
    comparison: str
    lhs_expr: Expr
    rhs_expr: Expr
    equality_lhs: str | None         # 등식이고 LHS가 단일 변수인 경우
    free_vars: frozenset[str]        # RHS에 등장하는 반복횟수 변수들
    compiled_lhs: Callable | None = None
    compiled_rhs: Callable | None = None
    args_tuple: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# ConstraintEngine
# ---------------------------------------------------------------------------

# SymPy 허용 함수 화이트리스트 (SRS §8.5)
_ALLOWED_SYMPY_FUNCTIONS = {
    "Abs": sympy.Abs,       # ABS()
    "round": sympy.Integer, # ROUND() — 정수 반올림
    "int": sympy.Integer,   # INT() — 정수 변환
    # 추가 안전 함수
    "floor": sympy.floor,
    "ceiling": sympy.ceiling,
}

# 허용 비교 연산자
_COMPARISON_OPS_ORDERED = (">=", "<=", ">", "<", "=")

# name.mw 패턴 (예: EO.mw, PLA-PEG-PLA.mw, H2O.mw)
# 성분 이름에는 영문자, 숫자, '-', '_'가 허용됨
_MW_SUFFIX_PATTERN = re.compile(r'([\w\-]+)\.mw', re.IGNORECASE)


def _substitute_mw_tokens(expr: str, mass_map: dict[str, float]) -> str:
    """
    제약식 문자열에서 `name.mw` 토큰을 실제 정밀질량 숫자로 치환한다.

    예:
        mass_map = {"EO": 44.026214, "LA": 72.021129}
        "EO * EO.mw + LA * LA.mw"
        → "EO * 44.026214 + LA * 72.021129"

    name.mw에서 name이 mass_map에 없으면 ConstraintParseError 발생.

    Args:
        expr:     전처리 전 제약식 (한쪽 변)
        mass_map: {성분이름: 정밀질량} 매핑

    Returns:
        name.mw가 숫자로 치환된 문자열

    Raises:
        ConstraintParseError: 알 수 없는 성분 이름의 .mw 사용
    """
    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name not in mass_map:
            raise ConstraintParseError(
                expr,
                f"'{name}.mw'에서 '{name}'은 정의되지 않은 성분입니다. "
                f"사용 가능한 성분: {', '.join(sorted(mass_map.keys()))}"
            )
        return repr(mass_map[name])   # float → 정밀한 문자열 표현

    return _MW_SUFFIX_PATTERN.sub(_replacer, expr)


def _preprocess_expression(expr: str, mass_map: dict[str, float]) -> str:
    """
    사용자 입력 표현식을 SymPy가 파싱할 수 있도록 전처리한다.

    처리 순서:
        1. name.mw → 정밀질량 숫자로 치환 (예: EO.mw → 44.026214)
        2. `^` → `**` (거듭제곱, SRS §8.3)
        3. `ABS(` → `Abs(` (SRS §8.5)
        4. `ROUND(` → `round(`
        5. `INT(` → `int(`

    Args:
        expr:     원본 표현식 문자열
        mass_map: {성분이름: 정밀질량} 매핑 (name.mw 치환용)

    Returns:
        전처리된 표현식 문자열
    """
    expr = expr.strip()
    # 1. name.mw 치환 (다른 처리보다 먼저 해야 "."이 연산자와 혼동되지 않음)
    expr = _substitute_mw_tokens(expr, mass_map)
    # 2. 거듭제곱
    expr = expr.replace("^", "**")
    # 3-5. 함수명 정규화
    expr = re.sub(r"\bABS\b", "Abs", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bROUND\b", "round", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bINT\b", "int", expr, flags=re.IGNORECASE)
    return expr


def _split_comparison(expression: str) -> tuple[str, str, str]:
    """
    제약식 문자열을 (lhs_str, operator, rhs_str)로 분리한다.

    SRS §8.4 Supported Comparisons: >= <= > < =

    Raises:
        ConstraintParseError: 비교 연산자가 없는 경우
    """
    for op in _COMPARISON_OPS_ORDERED:
        if op == "=":
            # '<=' 또는 '>='가 아닌 단독 '=' 찾기
            idx = -1
            for i, ch in enumerate(expression):
                if ch == "=" and i > 0 and expression[i-1] not in "<>!":
                    idx = i
                    break
            if idx >= 0:
                return expression[:idx].strip(), "=", expression[idx+1:].strip()
        else:
            if op in expression:
                parts = expression.split(op, maxsplit=1)
                return parts[0].strip(), op, parts[1].strip()

    raise ConstraintParseError(
        expression,
        f"비교 연산자({', '.join(_COMPARISON_OPS_ORDERED)})가 없습니다"
    )


class ConstraintEngine:
    """
    SymPy 기반 제약식 파서 + 평가기.

    SRS §8 Constraint Module 완전 구현.

    지원 연산자 (SRS §8.3): + - * / ^ ( )
    지원 비교  (SRS §8.4): = < <= > >=
    지원 함수  (SRS §8.5): ABS() ROUND() INT()

    변수 표기:
        name     — 성분의 반복 횟수 (정수 변수)
        name.mw  — 성분의 정밀질량 (상수, parse_all에 mass_map 필요)

    주요 기능:
        1. 제약식 파싱 (parse_all, mass_map 필요)
        2. 토폴로지 정렬로 평가 순서 결정
        3. 등식 제약식: 종속 변수 값 결정 (resolve)
        4. 불등식 제약식: 조성 검증 (evaluate)
        5. 순환 의존성 탐지 및 오류 보고

    사용 예:
        engine = ConstraintEngine()
        mass_map = {"EO": 44.026, "LA": 72.021, "HDI": 168.101}
        constraints = [Constraint("HDI = PLA + SMA - 1")]
        monomer_names = ["EO", "LA", "HDI", "PLA", "SMA"]

        parsed = engine.parse_all(constraints, monomer_names, mass_map)
        ordered = engine.topological_sort(parsed)

        partial = {"PLA": 2, "SMA": 10}
        hdi_val = engine.resolve(parsed[0], partial)  # 11

        # name.mw 사용 예:
        # "EO * EO.mw >= 1000" — EO 질량 합이 1000 Da 이상인 조성만 허용
    """

    def __init__(self) -> None:
        self._symbol_cache: dict[str, Symbol] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_all(
        self,
        constraints: list[Constraint],
        monomer_names: list[str],
        mass_map: dict[str, float] | None = None,
    ) -> list[ParsedConstraint]:
        """
        활성화된 모든 제약식을 파싱한다.

        Args:
            constraints:    Constraint 목록
            monomer_names:  허용된 변수명 목록 (Monomer.name)
            mass_map:       {성분이름: 정밀질량} 매핑.
                            name.mw 표기 사용 시 필수.
                            None이면 빈 딕셔너리로 처리.

        Returns:
            ParsedConstraint 리스트

        Raises:
            ConstraintParseError: 파싱 실패
        """
        if mass_map is None:
            mass_map = {}
        parsed = []
        for c in constraints:
            if not c.is_active:
                continue
            pc = self._parse_single(c.expression, monomer_names, mass_map)
            parsed.append(pc)
        return parsed

    def topological_sort(
        self, parsed: list[ParsedConstraint]
    ) -> list[ParsedConstraint]:
        """
        제약식 의존 그래프를 위상 정렬한다.

        등식 제약식 A = f(B, C)에서 A는 B, C에 의존하므로
        B, C를 결정하는 제약식이 A보다 먼저 평가되어야 한다.

        Q6 가정: 순환 의존성 발견 시 CircularDependencyError 발생.

        Args:
            parsed: ParsedConstraint 리스트

        Returns:
            위상 정렬된 리스트 (의존성 없는 것 먼저)

        Raises:
            CircularDependencyError: 순환 의존성 발견 시
        """
        # 각 제약식이 결정하는 변수 → 제약식 인덱스 매핑
        defines: dict[str, int] = {}
        for i, pc in enumerate(parsed):
            if pc.equality_lhs is not None:
                defines[pc.equality_lhs] = i

        # 의존 그래프: {인덱스: 먼저 평가해야 할 인덱스 집합}
        deps: dict[int, set[int]] = {i: set() for i in range(len(parsed))}
        for i, pc in enumerate(parsed):
            for var in pc.free_vars:
                if var in defines and defines[var] != i:
                    deps[i].add(defines[var])

        # Kahn's algorithm
        in_degree = {i: len(d) for i, d in deps.items()}
        queue = [i for i, d in in_degree.items() if d == 0]
        result: list[ParsedConstraint] = []

        while queue:
            node = queue.pop(0)
            result.append(parsed[node])
            defined_var = parsed[node].equality_lhs
            if defined_var:
                for j, dep_set in deps.items():
                    if node in dep_set:
                        dep_set.discard(node)
                        in_degree[j] -= 1
                        if in_degree[j] == 0:
                            queue.append(j)

        if len(result) != len(parsed):
            # 순환 의존성 존재 — 사이클 추적
            cycle = self._find_cycle(deps, parsed)
            raise CircularDependencyError(cycle)

        return result

    def resolve(
        self,
        parsed: ParsedConstraint,
        values: dict[str, int],
    ) -> int | None:
        """
        등식 제약식의 좌변 변수를 우변으로 계산한다.

        Q3 가정: 비정수 결과 → None 반환 (해당 후보 제거)

        Args:
            parsed: ParsedConstraint (equality_lhs가 있는 것)
            values: 현재까지 결정된 변수 값 딕셔너리

        Returns:
            계산된 정수값. 비정수이거나 음수이면 None.

        Raises:
            ConstraintEvalError: 평가 중 오류
        """
        if parsed.equality_lhs is None:
            return None

        try:
            args = [values.get(name, 0) for name in parsed.args_tuple]
            result = float(parsed.compiled_rhs(*args))
        except Exception as exc:
            raise ConstraintEvalError(
                parsed.original,
                f"우변 계산 실패: {exc}"
            ) from exc

        # Q3: 비정수 결과는 None 반환
        rounded = round(result)
        if abs(result - rounded) > 1e-9:
            return None  # 비정수 → 해당 후보 제거

        if rounded < 0:
            return None  # 음수 반복 단위는 물리적으로 불가

        return int(rounded)

    def evaluate(
        self,
        parsed: ParsedConstraint,
        values: dict[str, int],
    ) -> bool:
        """
        주어진 조성이 제약식을 만족하는지 평가한다.

        Args:
            parsed: ParsedConstraint
            values: {변수명: 값} 딕셔너리

        Returns:
            True: 만족 / False: 위반

        Raises:
            ConstraintEvalError: 평가 중 오류
        """
        try:
            args = [values.get(name, 0) for name in parsed.args_tuple]
            lhs_val = float(parsed.compiled_lhs(*args))
            rhs_val = float(parsed.compiled_rhs(*args))
        except Exception as exc:
            raise ConstraintEvalError(
                parsed.original,
                f"수식 평가 실패: {exc}"
            ) from exc

        op = parsed.comparison
        if op == "=":
            return abs(lhs_val - rhs_val) < 1e-9
        elif op == "<":
            return lhs_val < rhs_val
        elif op == "<=":
            return lhs_val <= rhs_val
        elif op == ">":
            return lhs_val > rhs_val
        elif op == ">=":
            return lhs_val >= rhs_val
        else:
            raise ConstraintEvalError(parsed.original, f"알 수 없는 연산자: {op}")

    def validate_expression(
        self,
        expression: str,
        monomer_names: list[str],
        mass_map: dict[str, float] | None = None,
    ) -> list[str]:
        """
        제약식 표현식의 유효성을 검사한다.

        Args:
            expression:    검사할 표현식 문자열
            monomer_names: 허용된 변수명 목록
            mass_map:      {성분이름: 정밀질량} 매핑. None이면 name.mw 사용 불가.

        Returns:
            오류 메시지 리스트. 빈 리스트 = 정상.
        """
        errors: list[str] = []
        try:
            self._parse_single(expression, monomer_names, mass_map or {})
        except ConstraintParseError as exc:
            errors.append(exc.reason)
        return errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_single(
        self,
        expression: str,
        monomer_names: list[str],
        mass_map: dict[str, float] | None = None,
    ) -> ParsedConstraint:
        """단일 제약식 문자열을 ParsedConstraint로 변환한다."""
        if mass_map is None:
            mass_map = {}
        expr = expression.strip()
        if not expr:
            raise ConstraintParseError(expression, "빈 제약식")

        # 비교 연산자 분리 (name.mw 치환 전에 수행)
        try:
            lhs_str, op, rhs_str = _split_comparison(expr)
        except ConstraintParseError:
            raise

        # 전처리: name.mw 치환 + 연산자 정규화
        try:
            lhs_str = _preprocess_expression(lhs_str, mass_map)
            rhs_str = _preprocess_expression(rhs_str, mass_map)
        except ConstraintParseError:
            raise

        # SymPy 심볼 생성 (허용된 변수명만)
        local_dict = {name: self._get_symbol(name) for name in monomer_names}
        local_dict.update(_ALLOWED_SYMPY_FUNCTIONS)

        try:
            lhs_sympy = sympify(lhs_str, locals=local_dict, evaluate=True)
            rhs_sympy = sympify(rhs_str, locals=local_dict, evaluate=True)
        except Exception as exc:
            raise ConstraintParseError(
                expression, f"SymPy 파싱 실패: {exc}"
            ) from exc

        # 미지 변수 검사 (monomer_names에 없는 변수 사용 금지)
        # name.mw는 이미 숫자로 치환됐으므로 free_symbols에 포함되지 않음
        all_free = lhs_sympy.free_symbols | rhs_sympy.free_symbols
        unknown = {str(s) for s in all_free} - set(monomer_names)
        if unknown:
            raise ConstraintParseError(
                expression,
                f"정의되지 않은 변수: {', '.join(sorted(unknown))}. "
                f"사용 가능한 변수: {', '.join(monomer_names)}\n"
                f"💡 정밀질량 참조는 '이름.mw' 형식을 사용하세요 (예: EO.mw)"
            )

        # 등식 좌변 단일 변수 판별
        equality_lhs: str | None = None
        if op == "=" and isinstance(lhs_sympy, Symbol):
            equality_lhs = str(lhs_sympy)

        # free_vars: 반복횟수 변수만 포함 (name.mw는 이미 상수로 치환됨)
        free_vars = frozenset(str(s) for s in rhs_sympy.free_symbols)

        # Compile for speed
        all_symbols = sorted(list(set(monomer_names) & set(str(s) for s in all_free)))
        args_tuple = tuple(all_symbols)
        syms = [self._get_symbol(n) for n in args_tuple]
        
        compiled_lhs = lambdify(syms, lhs_sympy, "math")
        compiled_rhs = lambdify(syms, rhs_sympy, "math")

        return ParsedConstraint(
            original=expression,
            comparison=op,
            lhs_expr=lhs_sympy,
            rhs_expr=rhs_sympy,
            equality_lhs=equality_lhs,
            free_vars=free_vars,
            compiled_lhs=compiled_lhs,
            compiled_rhs=compiled_rhs,
            args_tuple=args_tuple,
        )

    def _get_symbol(self, name: str) -> Symbol:
        """변수명에 대한 SymPy Symbol을 캐시하여 반환한다."""
        if name not in self._symbol_cache:
            self._symbol_cache[name] = Symbol(name, integer=True, nonnegative=True)
        return self._symbol_cache[name]

    @staticmethod
    def _find_cycle(
        deps: dict[int, set[int]],
        parsed: list[ParsedConstraint],
    ) -> list[str]:
        """의존 그래프에서 사이클을 탐색하여 변수명 경로를 반환한다."""
        visited: set[int] = set()
        path: list[int] = []

        def dfs(node: int) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            path.append(node)
            for neighbor in deps.get(node, set()):
                if dfs(neighbor):
                    return True
            path.pop()
            visited.add(node)
            return False

        for i in range(len(parsed)):
            if dfs(i):
                break

        cycle_names = []
        for idx in path:
            var = parsed[idx].equality_lhs or f"식[{idx}]"
            cycle_names.append(var)
        if cycle_names:
            cycle_names.append(cycle_names[0])  # 사이클 완성

        return cycle_names
