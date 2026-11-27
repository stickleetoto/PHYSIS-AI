"""Safe symbolic and numerical backend for the Function and Calculus Labs.

The ordinary expression language is delegated to :mod:`symbolic_core`. This
module opts into only ``tan`` and the documented ``piecewise`` form; each
condition compares bare ``x`` with one finite numeric constant (or assigned
coefficient), and the final branch must use ``True``:

    piecewise((value, x < boundary), (other_value, True))

Supported comparisons are ``<``, ``<=``, ``>``, ``>=``, ``==``, and ``!=``.
Branch values use the same restricted arithmetic and one-argument functions as
the core parser. No Python expression is evaluated and no SymPy text parser is
used. Curves and result rows are built from the same substituted expressions.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import math
import re
from typing import Any

import sympy as sp

from . import symbolic_core as core
from .math_derivation import derivative_steps


X = sp.Symbol("x", real=True)
LAB_FUNCTIONS = {"tan": sp.tan}
LAB_CHARS = re.compile(r"[A-Za-z0-9_+*/^()., \t<>!=\-]+\Z", re.ASCII)
PARAMETERS = {"a", "b", "c"}
MAX_PIECEWISE_BRANCHES = 8
MAX_CURVE_POINTS = 241
MAX_TOTAL_CURVE_POINTS = 1200
MAX_TOTAL_CURVE_SEGMENTS = 64
MAX_DIVISIONS = 200


@dataclass
class LabExpression:
    parsed: core.Parsed
    # (branch value, effective condition, branch-specific domain guards).
    # Keeping branches separate prevents plotting from bridging jumps.
    piece_regions: list[tuple[sp.Expr, sp.Expr, list[sp.Expr]]] | None = None
    excluded_points: set[sp.Expr] | None = None


def _base_result(status: str, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "rows": [], "curves": [], "steps": []}
    if detail:
        result["detail"] = detail
    return result


def _exact(value: Any) -> str:
    return str(value)


def _numeric(value: float) -> str:
    return format(float(value), ".12g")


def _row(label: str, value: Any, kind: str = "exact", latex: str | None = None) -> dict[str, str]:
    text = _exact(value)
    item: dict[str, str] = {"label": label, "value": text, "kind": kind}
    if latex is not None:
        item["latex"] = latex
    elif isinstance(value, sp.Basic):
        item["latex"] = sp.latex(value)
    return item


def _number(value: Any, label: str, default: Any | None = None) -> sp.Rational:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{label}은 유한한 숫자여야 합니다.")
    try:
        number = sp.Rational(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label}은 유한한 숫자여야 합니다.") from exc
    if not number.is_finite or abs(number) > 10**6:
        raise ValueError(f"{label}의 절댓값은 10⁶ 이하의 유한한 수여야 합니다.")
    return number


def _params(raw: Any) -> dict[sp.Symbol, sp.Rational]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - PARAMETERS:
        raise ValueError("계수는 a, b, c만 지정할 수 있습니다.")
    result: dict[sp.Symbol, sp.Rational] = {}
    for name, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"계수 {name}은 유한한 숫자여야 합니다.")
        number = _number(value, f"계수 {name}")
        result[core.symbol(name)] = number
    return result


def _parse_value(node: ast.AST, params: dict[sp.Symbol, sp.Rational]) -> core.Parsed:
    try:
        parsed = core.parse(ast.unparse(node), extra_functions=LAB_FUNCTIONS)
    except (ValueError, SyntaxError, RecursionError) as exc:
        raise ValueError(str(exc)) from exc
    _check_names(parsed.names)
    missing = parsed.names & {core.symbol(name) for name in PARAMETERS} - params.keys()
    if missing:
        names = ", ".join(sorted(map(str, missing)))
        raise ValueError(f"계수 {names}의 값을 입력하세요.")
    return core.substitute(parsed, params)


def _check_names(names: set[sp.Symbol]) -> None:
    unknown = names - {X} - {core.symbol(name) for name in PARAMETERS}
    if unknown:
        raise ValueError("변수는 x와 계수 a, b, c만 사용할 수 있습니다.")


def _condition(node: ast.AST, params: dict[sp.Symbol, sp.Rational]) -> sp.Expr:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        raise ValueError("piecewise 조건은 x와 한 경계값의 비교 하나로 입력하세요.")
    left_parsed = _parse_value(node.left, params)
    right_parsed = _parse_value(node.comparators[0], params)
    left, right = left_parsed.expr, right_parsed.expr
    left_is_x = isinstance(node.left, ast.Name) and node.left.id == "x"
    right_node = node.comparators[0]
    right_is_x = isinstance(right_node, ast.Name) and right_node.id == "x"
    if left_is_x == right_is_x:
        raise ValueError("piecewise 조건은 x와 유한한 상수 계수의 비교여야 합니다.")
    threshold = right if left_is_x else left
    threshold_guards = right_parsed.guards if left_is_x else left_parsed.guards
    if threshold_guards or threshold.free_symbols or threshold.is_number is not True or threshold.is_finite is not True:
        raise ValueError("piecewise 경계는 정의된 유한 상수 또는 대입한 계수여야 합니다.")
    operators = {
        ast.Lt: sp.Lt,
        ast.LtE: sp.Le,
        ast.Gt: sp.Gt,
        ast.GtE: sp.Ge,
        ast.Eq: sp.Eq,
        ast.NotEq: sp.Ne,
    }
    constructor = operators.get(type(node.ops[0]))
    if constructor is None:
        raise ValueError("piecewise 조건은 <, <=, >, >=, ==, != 비교만 지원합니다.")
    condition = constructor(left, right, evaluate=False)
    if condition.free_symbols - {X}:
        raise ValueError("piecewise 조건은 계수 대입 후 x만 포함해야 합니다.")
    return condition


def _as_set(condition: sp.Expr) -> sp.Set:
    if condition is sp.true or condition is True:
        return sp.S.Reals
    if condition is sp.false or condition is False:
        return sp.S.EmptySet
    try:
        result = condition.as_set()
    except (NotImplementedError, ValueError, TypeError) as exc:
        raise core.Unverifiable("piecewise 조건의 실수 구간을 확정할 수 없습니다.") from exc
    if result.has(sp.ConditionSet):
        raise core.Unverifiable("piecewise 조건의 실수 구간을 확정할 수 없습니다.")
    return result


def _parse_piecewise(text: str, params: dict[sp.Symbol, sp.Rational]) -> LabExpression:
    if len(text) > 180 or not LAB_CHARS.fullmatch(text):
        raise ValueError("piecewise 수식에 허용되지 않은 문자 또는 길이가 있습니다.")
    try:
        tree = ast.parse(text.strip().replace("^", "**"), mode="eval").body
    except (ValueError, SyntaxError, RecursionError) as exc:
        raise ValueError("piecewise 수식의 괄호와 연산자를 확인하세요.") from exc
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise ValueError("piecewise 수식은 최대 80개 구문 노드를 지원합니다.")
    if not isinstance(tree, ast.Call) or not isinstance(tree.func, ast.Name) or tree.func.id != "piecewise":
        raise ValueError("piecewise는 piecewise((값, 조건), ..., (기본값, True)) 형식이어야 합니다.")
    if tree.keywords or not 2 <= len(tree.args) <= MAX_PIECEWISE_BRANCHES:
        raise ValueError("piecewise는 2개부터 8개까지의 분기를 지원합니다.")

    branches: list[tuple[sp.Expr, sp.Expr]] = []
    assigned_regions: list[tuple[sp.Expr, sp.Expr, list[sp.Expr]]] = []
    seen_default = False
    previous_conditions: list[sp.Expr] = []
    for index, item in enumerate(tree.args):
        if not isinstance(item, ast.Tuple) or len(item.elts) != 2:
            raise ValueError("각 piecewise 분기는 (값, 조건) 쌍이어야 합니다.")
        value_node, condition_node = item.elts
        value = _parse_value(value_node, params)
        is_default = isinstance(condition_node, ast.Constant) and condition_node.value is True
        if is_default:
            if index != len(tree.args) - 1 or seen_default:
                raise ValueError("True 기본 분기는 piecewise의 마지막에 한 번만 쓸 수 있습니다.")
            condition = sp.true
            seen_default = True
        else:
            if seen_default:
                raise ValueError("piecewise의 True 기본 분기 뒤에는 다른 분기를 쓸 수 없습니다.")
            condition = _condition(condition_node, params)
        active_condition = sp.And(condition, sp.Not(sp.Or(*previous_conditions))) if previous_conditions else condition
        branches.append((value.expr, condition))
        assigned_regions.append((value.expr, active_condition, list(value.guards)))
        if not is_default:
            previous_conditions.append(condition)
    if not seen_default:
        raise ValueError("piecewise의 마지막 분기는 (기본값, True)여야 합니다.")

    # Conditions select the first branch. Its own domain guards remain binding
    # in assigned_regions, including holes cancelled by symbolic simplification.
    expr = sp.Piecewise(*branches)
    names = set(expr.free_symbols) - {X}
    if names:
        raise ValueError("계수 값이 대입되지 않은 수식입니다.")
    return LabExpression(core.Parsed(expr, [], set(expr.free_symbols)), assigned_regions)


def _parse_expression(text: Any, params: dict[sp.Symbol, sp.Rational]) -> LabExpression:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("수식을 입력하세요.")
    if text.lstrip().startswith("piecewise("):
        return _parse_piecewise(text, params)
    parsed = core.parse(text, extra_functions=LAB_FUNCTIONS)
    _check_names(parsed.names)
    missing = parsed.names & {core.symbol(name) for name in PARAMETERS} - params.keys()
    if missing:
        names = ", ".join(sorted(map(str, missing)))
        raise ValueError(f"계수 {names}의 값을 입력하세요.")
    parsed = core.substitute(parsed, params)
    if parsed.expr.free_symbols - {X}:
        raise ValueError("계수 값이 대입되지 않은 수식입니다.")
    return LabExpression(parsed)


def _domain(parsed: LabExpression, x: sp.Symbol) -> sp.Set:
    if parsed.piece_regions is None:
        domain: sp.Set = sp.S.Reals
        for guard in parsed.parsed.guards:
            if guard.func is sp.Ne and guard.args[1] == 0 and getattr(guard.args[0], "func", None) is sp.cos:
                try:
                    domain -= sp.solveset(guard.args[0], x, domain=sp.S.Reals)
                except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
                    raise core.Unverifiable("탄젠트 정의역의 대칭성을 확정할 수 없습니다.") from exc
            else:
                domain = _restrict_guard(domain, guard, x)
        return domain
    regions = []
    for _, condition, guards in parsed.piece_regions:
        region = _as_set(condition)
        for guard in guards:
            if guard.func is sp.Ne and guard.args[1] == 0 and getattr(guard.args[0], "func", None) is sp.cos:
                try:
                    region -= sp.solveset(guard.args[0], x, domain=region)
                except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
                    raise core.Unverifiable("탄젠트 정의역의 대칭성을 확정할 수 없습니다.") from exc
            else:
                region = _restrict_guard(region, guard, x)
        if region is not sp.S.EmptySet:
            regions.append(region)
    return sp.Union(*regions) if regions else sp.S.EmptySet


def _reflect_set(domain: sp.Set) -> sp.Set:
    if domain in (sp.S.Reals, sp.S.EmptySet):
        return domain
    if isinstance(domain, sp.Interval):
        return sp.Interval(-domain.end, -domain.start,
                           left_open=domain.right_open, right_open=domain.left_open)
    if isinstance(domain, sp.FiniteSet):
        return sp.FiniteSet(*[-value for value in domain])
    if isinstance(domain, sp.Union):
        return sp.Union(*[_reflect_set(part) for part in domain.args])
    if isinstance(domain, sp.Intersection):
        return sp.Intersection(*[_reflect_set(part) for part in domain.args])
    if isinstance(domain, sp.Complement):
        return sp.Complement(*[_reflect_set(part) for part in domain.args])
    if isinstance(domain, sp.ImageSet):
        lam = domain.lamda
        return sp.ImageSet(sp.Lambda(lam.variables, -lam.expr), *domain.base_sets)
    raise core.Unverifiable("정의역의 대칭성을 확정할 수 없습니다.")


def _restrict_guard(domain: sp.Set, guard: sp.Expr, x: sp.Symbol) -> sp.Set:
    """Intersect a real set with one core guard, resolving tan poles when bounded."""
    lhs, rhs = guard.args if guard.func is sp.Ne else (None, None)
    if guard.func is sp.Ne and rhs == 0 and getattr(lhs, "func", None) is sp.cos:
        try:
            poles = sp.solveset(lhs, x, domain=domain)
        except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
            raise core.Unverifiable("탄젠트 특이점의 실수 위치를 확정할 수 없습니다.") from exc
        if poles is sp.S.EmptySet:
            return domain
        if not isinstance(poles, sp.FiniteSet):
            raise core.Unverifiable("유한 구간에서 탄젠트 특이점의 위치를 확정할 수 없습니다.")
        return domain - poles
    try:
        restriction = guard.as_set()
    except (NotImplementedError, ValueError, TypeError) as exc:
        raise core.Unverifiable("수식의 실수 정의역 조건을 확정할 수 없습니다.") from exc
    if restriction.has(sp.ConditionSet):
        raise core.Unverifiable("수식의 실수 정의역 조건을 확정할 수 없습니다.")
    return domain.intersect(restriction)


def _window_domain(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational, hi: sp.Rational) -> sp.Set:
    viewport = sp.Interval(lo, hi)
    if parsed.piece_regions is None:
        result: sp.Set = viewport
        for guard in parsed.parsed.guards:
            result = _restrict_guard(result, guard, x)
    else:
        regions: list[sp.Set] = []
        for _, condition, guards in parsed.piece_regions:
            region = _as_set(condition).intersect(viewport)
            for guard in guards:
                region = _restrict_guard(region, guard, x)
            if region is not sp.S.EmptySet:
                regions.append(region)
        result = sp.Union(*regions) if regions else sp.S.EmptySet
    if parsed.excluded_points:
        result -= sp.FiniteSet(*(p for p in parsed.excluded_points if lo <= p <= hi))
    if result.has(sp.ConditionSet):
        raise core.Unverifiable("계산 범위에서 정의역을 확정할 수 없습니다.")
    return result


def _window_regions(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                    hi: sp.Rational) -> list[tuple[sp.Expr, sp.Set]]:
    viewport = sp.Interval(lo, hi)
    if parsed.piece_regions is None:
        return [(parsed.parsed.expr, _window_domain(parsed, x, lo, hi))]
    regions = []
    for expr, condition, guards in parsed.piece_regions:
        region = _as_set(condition).intersect(viewport)
        for guard in guards:
            region = _restrict_guard(region, guard, x)
        if region is not sp.S.EmptySet:
            regions.append((expr, region))
    if parsed.excluded_points:
        excluded = sp.FiniteSet(*(p for p in parsed.excluded_points if lo <= p <= hi))
        regions = [(expr, region - excluded) for expr, region in regions]
    return regions


def _components(domain: sp.Set) -> list[sp.Set]:
    if domain is sp.S.EmptySet:
        return []
    parts = list(sp.Union.make_args(domain))
    def key(part: sp.Set) -> float:
        if isinstance(part, sp.Interval):
            return float(part.start)
        if isinstance(part, sp.FiniteSet) and part:
            return float(min(part, key=lambda value: float(value)))
        return math.inf
    parts.sort(key=key)
    return parts


def _real_value(expr: sp.Expr, x: sp.Symbol, at: sp.Expr) -> float | None:
    try:
        return core.scalar(sp.N(expr.subs(x, at), 16))
    except (TypeError, ValueError, ArithmeticError, OverflowError, core.Unverifiable):
        return None


def _curve_segments(expr: sp.Expr, x: sp.Symbol, domain: sp.Set, lo: sp.Rational,
                    hi: sp.Rational, max_points: int = MAX_CURVE_POINTS,
                    max_total_points: int = MAX_TOTAL_CURVE_POINTS,
                    budget: list[int] | None = None) -> list[list[list[float]]]:
    viewport = sp.Interval(lo, hi)
    clipped = domain.intersect(viewport)
    curves: list[list[list[float]]] = []
    span = float(hi - lo)
    parts = _components(clipped)
    if len(parts) > MAX_TOTAL_CURVE_SEGMENTS or len(parts) > max_total_points:
        raise core.Unverifiable("그래프 구간 수가 안전 한도를 넘었습니다.")
    if budget is None:
        budget = [0]
    for part in parts:
        if isinstance(part, sp.FiniteSet):
            for point in sorted(part, key=float):
                budget[0] += 1
                if budget[0] > max_total_points:
                    raise core.Unverifiable("그래프 표본 수가 안전 한도를 넘었습니다.")
                value = _real_value(expr, x, point)
                if value is not None:
                    curves.append([[float(point), value]])
            continue
        if not isinstance(part, sp.Interval):
            raise core.Unverifiable("그래프의 연속 구간을 확정할 수 없습니다.")
        width = part.end - part.start
        if width <= 0:
            continue
        count = max(4, min(max_points, round(max_points * float(width) / span)))
        segment: list[list[float]] = []
        for index in range(count + 1):
            if (index == 0 and part.left_open) or (index == count and part.right_open):
                continue
            budget[0] += 1
            if budget[0] > max_total_points:
                raise core.Unverifiable("그래프 표본 수가 안전 한도를 넘었습니다.")
            at = part.start + width * sp.Rational(index, count)
            value = _real_value(expr, x, at)
            if value is None:
                if segment:
                    curves.append(segment)
                    segment = []
            else:
                segment.append([float(at), value])
        if segment:
            curves.append(segment)
    return curves


def _curve(label: str, expr: sp.Expr, parsed: LabExpression, x: sp.Symbol,
           lo: sp.Rational, hi: sp.Rational) -> dict[str, Any]:
    segments: list[list[list[float]]] = []
    budget = [0]
    for _, region in _window_regions(parsed, x, lo, hi):
        remaining = MAX_TOTAL_CURVE_POINTS - budget[0]
        if remaining < 1:
            raise core.Unverifiable("그래프 표본 수가 안전 한도를 넘었습니다.")
        segments.extend(_curve_segments(expr, x, region, lo, hi,
                                        max_total_points=MAX_TOTAL_CURVE_POINTS, budget=budget))
        if len(segments) > MAX_TOTAL_CURVE_SEGMENTS:
            raise core.Unverifiable("그래프 구간 수가 안전 한도를 넘었습니다.")
    return {"label": label, "segments": segments}


def _finite_points(solution: sp.Set, lo: sp.Rational, hi: sp.Rational) -> list[sp.Expr] | None:
    if solution is sp.S.EmptySet:
        return []
    if not isinstance(solution, sp.FiniteSet):
        return None
    values = [sp.simplify(value) for value in solution if value.is_real is not False
              and value.is_finite is not False and lo <= value <= hi]
    values.sort(key=float)
    return values


def _solve_points(expr: sp.Expr, x: sp.Symbol, domain: sp.Set,
                  lo: sp.Rational, hi: sp.Rational) -> list[sp.Expr] | None:
    try:
        solved = sp.solveset(expr, x, domain=domain)
    except (NotImplementedError, ValueError, TypeError, RecursionError):
        return None
    return _finite_points(solved, lo, hi)


def _point_list(values: list[sp.Expr]) -> str:
    return ", ".join(_exact(sp.simplify(value)) for value in values) if values else "없음"


def _critical_points(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                     hi: sp.Rational) -> tuple[list[tuple[str, sp.Expr, sp.Expr, str]], bool]:
    domain = _window_domain(parsed, x, lo, hi)
    derivative = sp.diff(parsed.parsed.expr, x)
    if derivative.has(sp.Derivative, sp.DiracDelta, sp.Integral):
        return [], False
    candidates = _solve_points(derivative, x, domain, lo, hi)
    complete = candidates is not None
    candidates = candidates or []
    second = sp.diff(parsed.parsed.expr, x, 2)
    result: list[tuple[str, sp.Expr, sp.Expr, str]] = []
    boundaries = _derivative_breaks(parsed, x, lo, hi)
    for point in sorted(boundaries, key=float):
        if domain.contains(point) is not sp.true:
            continue
        value = parsed.parsed.expr.subs(x, point)
        sides = [_one_sided_value(parsed,x,point,d) for d in ("-", "+")]
        if any(v is None or v != value for v in sides):
            complete = False
            continue
        left, right = [_one_sided_value(parsed,x,point,d,order=1) for d in ("-", "+")]
        if left is None or right is None:
            complete = False
        elif left.is_negative and right.is_positive:
            result.append(("극솟값",point,value,"exact"))
        elif left.is_positive and right.is_negative:
            result.append(("극댓값",point,value,"exact"))
        else:
            complete = False
    for point in candidates:
        if point in boundaries:
            continue
        value = sp.simplify(parsed.parsed.expr.subs(x, point))
        curvature = sp.simplify(second.subs(x, point))
        if curvature.is_positive is True:
            kind, evidence = "극솟값", "exact"
        elif curvature.is_negative is True:
            kind, evidence = "극댓값", "exact"
        else:
            delta = sp.Rational(1, 10000)
            left = _real_value(parsed.parsed.expr, x, point - delta)
            center = _real_value(parsed.parsed.expr, x, point)
            right = _real_value(parsed.parsed.expr, x, point + delta)
            if left is None or center is None or right is None:
                continue
            if center <= left and center <= right and (center < left or center < right):
                kind, evidence = "극솟값", "numeric"
            elif center >= left and center >= right and (center > left or center > right):
                kind, evidence = "극댓값", "numeric"
            else:
                complete = False
                continue
        result.append((kind, point, value, evidence))
    return result, complete


def _inflection_points(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                       hi: sp.Rational) -> tuple[list[sp.Tuple], bool]:
    expr = parsed.parsed.expr
    second, third = sp.diff(expr, x, 2), sp.diff(expr, x, 3)
    if second.has(sp.Derivative, sp.DiracDelta, sp.Integral):
        return [], False
    domain = _window_domain(parsed, x, lo, hi)
    candidates = _solve_points(second, x, domain, lo, hi)
    if candidates is None:
        return [], False
    points = []
    complete = True
    for at in candidates:
        slope = sp.simplify(third.subs(x, at))
        if slope.is_zero is False and slope.is_real is True:
            points.append(sp.Tuple(at, sp.simplify(expr.subs(x, at))))
        elif slope.is_zero is not True:
            complete = False
    return points, complete


def _monotonic_intervals(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                         hi: sp.Rational) -> tuple[list[str], list[str], bool]:
    derivative = sp.diff(parsed.parsed.expr, x)
    if derivative.has(sp.Derivative, sp.DiracDelta, sp.Integral):
        return [], [], False
    increasing: list[str] = []
    decreasing: list[str] = []
    complete = True
    for _, region in _window_regions(parsed, x, lo, hi):
        for part in _components(region):
            if not isinstance(part, sp.Interval):
                continue
            roots = _solve_points(derivative, x, part, part.start, part.end)
            if roots is None:
                complete = False
                continue
            edges = [part.start, *[root for root in roots if part.start < root < part.end], part.end]
            for start, end in zip(edges, edges[1:]):
                if start >= end:
                    continue
                sample = sp.Rational(str((float(start) + float(end)) / 2))
                value = sp.simplify(derivative.subs(x, sample))
                text = f"({start}, {end})"
                if value.is_positive is True:
                    increasing.append(text)
                elif value.is_negative is True:
                    decreasing.append(text)
                else:
                    complete = False
    return increasing, decreasing, complete


def _asymptotes(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                hi: sp.Rational) -> tuple[list[sp.Expr], list[sp.Expr], bool]:
    expr = parsed.parsed.expr
    domain = _window_domain(parsed, x, lo, hi)
    candidates: set[sp.Expr] = set()
    regions = _window_regions(parsed, x, lo, hi)
    for _, region in regions:
        for part in _components(region):
            if isinstance(part, sp.Interval):
                for endpoint in (part.start, part.end):
                    if endpoint.is_finite and lo <= endpoint <= hi:
                        candidates.add(sp.simplify(endpoint))
    vertical: list[sp.Expr] = []
    complete = True
    for point in sorted(candidates, key=float):
        near_domain = _window_domain(parsed, x, point - 1, point + 1)
        sides = []
        for direction in ("-", "+"):
            near = sp.Interval.open(point - 1, point) if direction == "-" else sp.Interval.open(point, point + 1)
            sides.append(near_domain.intersect(near).is_empty is False)
        try:
            one_sided = [sp.limit(expr, x, point, dir=direction) if available else None
                         for direction, available in zip(("-", "+"), sides)]
        except (NotImplementedError, ValueError, TypeError, RecursionError):
            complete = False
            continue
        if any(value in (sp.oo, -sp.oo) for value in one_sided if value is not None):
            vertical.append(point)
        elif any(value is not None and (value.has(sp.zoo, sp.nan, sp.I) or value.is_real is False)
                 for value in one_sided):
            complete = False
    horizontal: list[sp.Expr] = []
    for direction in ("-", "+"):
        try:
            value = sp.limit(expr, x, -sp.oo if direction == "-" else sp.oo)
        except (NotImplementedError, ValueError, TypeError, RecursionError):
            complete = False
            continue
        if value.is_number and value.is_finite is True and value.is_real is True and not value.has(sp.AccumBounds, sp.Limit):
            value = sp.simplify(value)
            if value not in horizontal:
                horizontal.append(value)
        elif value.has(sp.AccumBounds, sp.zoo, sp.nan, sp.I):
            complete = False
    return vertical, horizontal, complete


def _function_mode(parsed: LabExpression, other: LabExpression | None, x: sp.Symbol,
                   lo: sp.Rational, hi: sp.Rational, point: sp.Rational | None) -> dict[str, Any]:
    result = _base_result("ok")
    expr = parsed.parsed.expr
    domain = _window_domain(parsed, x, lo, hi)
    result["rows"].append(_row("수식", expr))
    result["rows"].append(_row("정의역 (창)", domain, "note"))
    result["curves"].append(_curve("f(x)", expr, parsed, x, lo, hi))

    roots = _solve_points(expr, x, domain, lo, hi)
    result["rows"].append(_row("x절편", _point_list(roots) if roots is not None else "창 안의 모든 해를 확정할 수 없음",
                               "exact" if roots is not None else "note"))
    zero_domain = _window_domain(parsed, x, sp.Rational(-1), sp.Rational(1))
    at_zero = sp.simplify(expr.subs(x, sp.S.Zero)) if zero_domain.contains(0) is sp.true else None
    if at_zero is not None and (at_zero.has(sp.zoo, sp.nan, sp.oo, -sp.oo) or at_zero.is_real is False):
        at_zero = None
    result["rows"].append(_row("y절편", at_zero if at_zero is not None else "정의되지 않음",
                               "exact" if at_zero is not None else "note"))
    if point is not None:
        point_domain = _window_domain(parsed, x, point - 1, point + 1)
        at_point = sp.simplify(expr.subs(x, point)) if point_domain.contains(point) is sp.true else None
        if at_point is not None and (at_point.has(sp.zoo, sp.nan, sp.oo, -sp.oo) or at_point.is_real is False):
            at_point = None
        result["rows"].append(_row(f"f({_exact(point)})", at_point if at_point is not None else "정의되지 않음",
                                   "exact" if at_point is not None else "note"))
    extrema, extrema_complete = _critical_points(parsed, x, lo, hi)
    for kind in ("극댓값", "극솟값"):
        points = [sp.Tuple(at, value) for item_kind, at, value, evidence in extrema
                  if item_kind == kind and evidence == "exact"]
        numeric = [sp.Tuple(at, value) for item_kind, at, value, evidence in extrema
                   if item_kind == kind and evidence == "numeric"]
        empty = f"확인된 {kind} 없음" if extrema_complete else "미확정"
        result["rows"].append(_row(kind, ", ".join(map(str, points)) if points else empty,
                                   "exact" if points else "note"))
        if numeric:
            result["rows"].append(_row(f"수치 {kind} 후보", ", ".join(map(str, numeric)), "numeric"))
    inflections, inflections_complete = _inflection_points(parsed, x, lo, hi)
    result["rows"].append(_row("변곡점", ", ".join(map(str, inflections)) if inflections else
                               ("확인된 변곡점 없음" if inflections_complete else "미확정"),
                               "exact" if inflections else "note"))
    increasing, decreasing, monotonic_complete = _monotonic_intervals(parsed, x, lo, hi)
    result["rows"].append(_row("증가 구간", ", ".join(increasing) if increasing else
                               ("확인된 증가 구간 없음" if monotonic_complete else "미확정"),
                               "exact" if increasing else "note"))
    result["rows"].append(_row("감소 구간", ", ".join(decreasing) if decreasing else
                               ("확인된 감소 구간 없음" if monotonic_complete else "미확정"),
                               "exact" if decreasing else "note"))
    vertical, horizontal, asymptote_complete = _asymptotes(parsed, x, lo, hi)
    result["guides"] = {"vertical": [float(v) for v in vertical],
                        "horizontal": [float(v) for v in horizontal]}
    if parsed.piece_regions is None and expr.is_rational_function(x):
        numerator, denominator = sp.cancel(expr).as_numer_denom()
        if sp.degree(denominator, x) > 0:
            quotient, remainder = sp.div(numerator, denominator, x)
            if remainder != 0 and sp.degree(quotient, x) == 1:
                result["rows"].append(_row("사선점근선", quotient))
                result["curves"].append({"label": "사선점근선", "segments": [[
                    [float(lo), float(quotient.subs(x, lo))],
                    [float(hi), float(quotient.subs(x, hi))]]]})
    result["rows"].append(_row("수직점근선", ", ".join(f"x = {value}" for value in vertical) if vertical else
                               ("확인된 수직점근선 없음" if asymptote_complete else "미확정"),
                               "exact" if vertical else "note"))
    result["rows"].append(_row("수평점근선", ", ".join(f"y = {value}" for value in horizontal) if horizontal else
                               ("확인된 수평점근선 없음" if asymptote_complete else "미확정"),
                               "exact" if horizontal else "note"))
    even = sp.simplify(expr.subs(x, -x) - expr) == 0
    odd = sp.simplify(expr.subs(x, -x) + expr) == 0
    if not even and not odd:
        symmetry = "해당 없음"
    else:
        try:
            full_domain = _domain(parsed, x)
            reflected = _reflect_set(full_domain)
            symmetric = full_domain.symmetric_difference(reflected).is_empty
            symmetry = ("우함수" if even else "기함수") if symmetric is True else \
                "해당 없음" if symmetric is False else "미확정"
        except (core.Unverifiable, NotImplementedError, ValueError, TypeError):
            symmetry = "미확정"
    result["rows"].append(_row("대칭성", symmetry, "note"))

    if other is not None:
        other_expr = other.parsed.expr
        other_domain = _window_domain(other, x, lo, hi)
        result["rows"].append(_row("g(x)", other_expr))
        result["curves"].append(_curve("g(x)", other_expr, other, x, lo, hi))
        common = domain.intersect(other_domain)
        intersections = _solve_points(expr - other_expr, x, common, lo, hi)
        if intersections is None:
            text = "창 안의 모든 교점을 확정할 수 없음"
        else:
            pairs = [sp.Tuple(point, sp.simplify(expr.subs(x, point))) for point in intersections]
            text = ", ".join(map(str, pairs)) if pairs else "없음"
        result["rows"].append(_row("교점", text, "exact" if intersections is not None else "note"))
    return result


def _limit(expr: sp.Expr, x: sp.Symbol, point: sp.Expr, direction: str) -> sp.Expr:
    try:
        value = sp.limit(expr, x, point, dir=direction)
    except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
        raise core.Unverifiable("이 방향의 극한을 확정할 수 없습니다.") from exc
    if value.has(sp.AccumBounds, sp.zoo, sp.nan, sp.I):
        raise core.Unverifiable("진동하거나 실수로 확정할 수 없는 극한입니다.")
    if value not in (sp.oo, -sp.oo) and value.is_real is False:
        raise core.Unverifiable("실수 범위의 극한을 확정할 수 없습니다.")
    return sp.simplify(value)


def _one_sided_value(parsed: LabExpression, x: sp.Symbol, point: sp.Expr,
                     direction: str, order: int = 0, step: sp.Rational = sp.Rational(1, 10)) -> sp.Expr | None:
    if parsed.piece_regions is None:
        expression = sp.diff(parsed.parsed.expr, x, order) if order else parsed.parsed.expr
        return _limit(expression, x, point, direction)
    lo, hi = point - step, point + step
    matches: list[sp.Expr] = []
    for branch_expr, region in _window_regions(parsed, x, lo, hi):
        for part in _components(region):
            if not isinstance(part, sp.Interval):
                continue
            adjacent = (part.start < point and part.end >= point) if direction == "-" else \
                (part.start <= point and part.end > point)
            if adjacent:
                branch = sp.diff(branch_expr, x, order) if order else branch_expr
                matches.append(_limit(branch, x, point, direction))
    if not matches:
        return None
    if any(sp.simplify(value - matches[0]) != 0 for value in matches[1:]):
        raise core.Unverifiable("이 방향에서 piecewise 분기 극한을 하나로 확정할 수 없습니다.")
    return matches[0]


def _finite_real(value: sp.Expr) -> bool:
    return value.is_finite is True and value.is_real is True


def _differentiable_at(parsed: LabExpression, x: sp.Symbol, point: sp.Expr,
                       step: sp.Rational) -> bool | None:
    domain = _window_domain(parsed, x, point - step, point + step)
    if domain.contains(point) is not sp.true:
        return False
    at = sp.simplify(parsed.parsed.expr.subs(x, point))
    if not _finite_real(at):
        return False
    try:
        left_value = _one_sided_value(parsed, x, point, "-", step=step)
        right_value = _one_sided_value(parsed, x, point, "+", step=step)
        left_slope = _one_sided_value(parsed, x, point, "-", order=1, step=step)
        right_slope = _one_sided_value(parsed, x, point, "+", order=1, step=step)
    except core.Unverifiable:
        return None
    if left_value is None or right_value is None or left_slope is None or right_slope is None:
        return False
    if not all(_finite_real(value) for value in (left_value, right_value, left_slope, right_slope)):
        return False
    return all(sp.simplify(a - b) == 0 for a, b in (
        (left_value, at), (right_value, at), (left_slope, right_slope)))


def _derivative_breaks(parsed: LabExpression, x: sp.Symbol, lo: sp.Rational,
                       hi: sp.Rational) -> set[sp.Expr]:
    candidates: set[sp.Expr] = set()
    if parsed.piece_regions is not None:
        for _, region in _window_regions(parsed, x, lo, hi):
            for part in _components(region):
                if isinstance(part, sp.Interval):
                    for endpoint in (part.start, part.end):
                        if endpoint.is_finite and lo <= endpoint <= hi:
                            candidates.add(sp.simplify(endpoint))
    window = _window_domain(parsed, x, lo, hi)
    for node in sp.preorder_traversal(parsed.parsed.expr):
        if node.func is sp.Abs:
            roots = _solve_points(node.args[0], x, window, lo, hi)
            if roots is None:
                continue
            candidates.update(roots)
    breaks = set()
    for point in candidates:
        if lo < point < hi and _differentiable_at(parsed, x, point, sp.Rational(1, 100)) is not True:
            breaks.add(point)
    return breaks


def _limit_mode(parsed: LabExpression, x: sp.Symbol, point: sp.Rational, step: sp.Rational,
                lo: sp.Rational, hi: sp.Rational) -> dict[str, Any]:
    expr = parsed.parsed.expr
    domain = _window_domain(parsed, x, min(lo, point - step), max(hi, point + step))

    def approaches(direction: str) -> bool:
        for divisor in (1, 2, 4, 8):
            epsilon = step / divisor
            near = sp.Interval.open(point - epsilon, point) if direction == "-" else sp.Interval.open(point, point + epsilon)
            intersection = domain.intersect(near)
            if intersection is not sp.S.EmptySet and intersection.is_empty is not True:
                return True
        return False

    has_left, has_right = approaches("-"), approaches("+")
    left = _one_sided_value(parsed, x, point, "-", step=step) if has_left else None
    right = _one_sided_value(parsed, x, point, "+", step=step) if has_right else None
    if left is None and right is None:
        raise core.Unverifiable("점의 양쪽에 실수 정의역이 없어 극한을 조사할 수 없습니다.")
    result = _base_result("ok")
    unavailable = "실수 정의역에서 접근 불가"
    result["rows"].extend((_row("좌극한", left if left is not None else unavailable,
                                "exact" if left is not None else "note"),
                           _row("우극한", right if right is not None else unavailable,
                                "exact" if right is not None else "note")))
    both = False
    if left is not None and right is not None:
        both = sp.simplify(left - right) == 0 if left.is_finite is True and right.is_finite is True else left == right
    result["rows"].append(_row("양측 극한", left if both else "존재하지 않음", "exact" if both else "note"))
    at_point = sp.simplify(expr.subs(x, point))
    function_defined = domain.contains(point) is sp.true and _finite_real(at_point)
    if not function_defined:
        result["rows"].append(_row("함수값", "정의되지 않음", "note"))
    else:
        result["rows"].append(_row("함수값", at_point))
    if function_defined and left is not None and right is not None and _finite_real(left) and _finite_real(right):
        continuity = "연속" if all(sp.simplify(a - b) == 0 for a, b in ((left, at_point), (right, at_point))) else "불연속"
    elif function_defined and ((left is None) != (right is None)):
        one_side = right if left is None else left
        continuity = "정의역 끝점에서 상대 연속" if _finite_real(one_side) and sp.simplify(one_side - at_point) == 0 else "불연속"
    else:
        continuity = "불연속" if function_defined else "불연속"
    result["rows"].append(_row("연속성", continuity, "exact"))
    result["curves"].append(_curve("f(x)", expr, parsed, x, lo, hi))
    sample_left: list[list[float]] = []
    sample_right: list[list[float]] = []
    for exponent in range(1, 9):
        offset = step / 2**(exponent - 1)
        for direction, destination, at in (("-", sample_left, point - offset), ("+", sample_right, point + offset)):
            if ((direction == "-" and has_left) or (direction == "+" and has_right)) and domain.contains(at) is sp.true:
                value = _real_value(expr, x, at)
                if value is not None:
                    destination.append([float(at), value])
            if exponent == 1:
                result["steps"].append(f"h={_exact(offset)}에서 {at}: 함수값 접근 표본")
    if sample_left:
        result["curves"].append({"label": "좌극한 표본", "segments": [[point] for point in sample_left]})
    if sample_right:
        result["curves"].append({"label": "우극한 표본", "segments": [[point] for point in sample_right]})
    result["guides"] = {"vertical": [float(point)]}
    return result


def _derivative_mode(parsed: LabExpression, x: sp.Symbol, point: sp.Rational | None,
                     step: sp.Rational, lo: sp.Rational, hi: sp.Rational) -> dict[str, Any]:
    expr = parsed.parsed.expr
    derivative = sp.simplify(sp.diff(expr, x))
    if derivative.has(sp.Derivative, sp.Integral, sp.DiracDelta):
        raise core.Unverifiable("지원 범위에서 도함수를 확정할 수 없습니다.")
    second = sp.simplify(sp.diff(derivative, x))
    result = _base_result("ok")
    result["rows"].extend((_row("수식", expr), _row("도함수", derivative)))
    if second.has(sp.DiracDelta, sp.Derivative):
        result["rows"].append(_row("이계도함수", "매끄러운 구간별로 해석해야 합니다.", "note"))
    else:
        result["rows"].append(_row("이계도함수", second))
    result["steps"].extend(derivative_steps(expr, x))
    result["curves"].append(_curve("f(x)", expr, parsed, x, lo, hi))
    derivative_regions = None
    if parsed.piece_regions is not None:
        derivative_regions = [(sp.diff(branch, x), condition, guards)
                              for branch, condition, guards in parsed.piece_regions]
    derivative_parsed = LabExpression(core.Parsed(derivative, parsed.parsed.guards, parsed.parsed.names),
                                      derivative_regions, _derivative_breaks(parsed, x, lo, hi))
    result["curves"].append(_curve("f′(x)", derivative, derivative_parsed, x, lo, hi))
    extrema, extrema_complete = _critical_points(parsed, x, lo, hi)
    for kind, label in (("극댓값", "극대"), ("극솟값", "극소")):
        values = [sp.Tuple(at, val) for item_kind, at, val, evidence in extrema
                  if item_kind == kind and evidence == "exact"]
        empty = f"확인된 {label} 없음" if extrema_complete else "미확정"
        result["rows"].append(_row(label, ", ".join(map(str, values)) if values else empty,
                                   "exact" if values else "note"))
        numeric = [sp.Tuple(at, val) for item_kind, at, val, evidence in extrema
                   if item_kind == kind and evidence == "numeric"]
        if numeric:
            result["rows"].append(_row(f"수치 {label} 후보", ", ".join(map(str, numeric)), "numeric"))
    inflections, inflections_complete = _inflection_points(parsed, x, lo, hi)
    result["rows"].append(_row("변곡점", ", ".join(map(str, inflections)) if inflections else
                               ("확인된 변곡점 없음" if inflections_complete else "미확정"),
                               "exact" if inflections else "note"))
    increasing, decreasing, monotonic_complete = _monotonic_intervals(parsed, x, lo, hi)
    result["rows"].append(_row("증가 구간", ", ".join(increasing) if increasing else
                               ("확인된 증가 구간 없음" if monotonic_complete else "미확정"),
                               "exact" if increasing else "note"))
    result["rows"].append(_row("감소 구간", ", ".join(decreasing) if decreasing else
                               ("확인된 감소 구간 없음" if monotonic_complete else "미확정"),
                               "exact" if decreasing else "note"))
    if point is not None:
        domain = _window_domain(parsed, x, min(point - step, lo), max(point + step, hi))
        if domain.contains(point) is not sp.true:
            raise core.Unverifiable("접점이 함수의 실수 정의역에 없습니다.")
        function_value = sp.simplify(expr.subs(x, point))
        left_function = _one_sided_value(parsed, x, point, "-", step=step)
        right_function = _one_sided_value(parsed, x, point, "+", step=step)
        if left_function is None or right_function is None or not _finite_real(function_value) or \
                not _finite_real(left_function) or not _finite_real(right_function) or \
                sp.simplify(left_function - function_value) != 0 or \
                sp.simplify(right_function - function_value) != 0:
            raise core.Unverifiable("접점에서 함수가 연속임을 확인할 수 없습니다.")
        left_slope = _one_sided_value(parsed, x, point, "-", order=1, step=step)
        right_slope = _one_sided_value(parsed, x, point, "+", order=1, step=step)
        if left_slope is None or right_slope is None:
            raise core.Unverifiable("접점에서 양쪽 실수 도함수를 확인할 수 없습니다.")
        if sp.simplify(left_slope - right_slope) != 0:
            raise core.Unverifiable("접점에서 좌우 도함수가 달라 미분할 수 없습니다.")
        slope = sp.simplify(left_slope)
        if not _finite_real(slope):
            raise core.Unverifiable("접점에서 함수값 또는 도함수가 유한하지 않습니다.")
        tangent = sp.expand(slope * (x - point) + function_value)
        result["rows"].extend((_row("접점의 도함수", slope),
                               _row("접선", f"y = {tangent}")))
        result["curves"].append({"label": "접선", "segments": [[
            [float(lo), float(sp.N(tangent.subs(x, lo)))],
            [float(hi), float(sp.N(tangent.subs(x, hi)))],
        ]]})
        if step > 0:
            right_point = point + step
            if domain.contains(right_point) is sp.true:
                average = sp.simplify((expr.subs(x, right_point) - function_value) / step)
                result["rows"].append(_row("평균변화율", average))
                result["steps"].append(f"할선 기울기 = (f({right_point}) - f({point})) / {step} = {average}")
                right_value = _real_value(expr, x, right_point)
                if right_value is not None:
                    result["curves"].append({"label": "할선", "segments": [[
                        [float(point), float(sp.N(function_value))],
                        [float(right_point), right_value],
                    ]]})
        result["steps"].append(f"접선 방정식: y - {function_value} = {slope}(x - {point})")
        result["guides"] = {"vertical": [float(point)]}
    return result


def _integral_value(expr: sp.Expr, x: sp.Symbol, lower: sp.Rational,
                    upper: sp.Rational, divisions: int, rule: str) -> float:
    width = float(upper - lower)
    dx = width / divisions
    def f(index: float) -> float:
        at = sp.Rational(str(float(lower) + index * dx))
        value = _real_value(expr, x, at)
        if value is None:
            raise core.Unverifiable("수치 적분 구간 안에서 실수 함수값을 얻지 못했습니다.")
        return value
    if rule == "left":
        return dx * sum(f(index) for index in range(divisions))
    if rule == "midpoint":
        return dx * sum(f(index + .5) for index in range(divisions))
    if rule == "trapezoid":
        return dx * (.5 * f(0) + sum(f(index) for index in range(1, divisions)) + .5 * f(divisions))
    if divisions % 2:
        raise ValueError("Simpson 근사를 위해 분할 개수를 짝수로 입력하세요.")
    return dx / 3 * (f(0) + f(divisions) + 4 * sum(f(index) for index in range(1, divisions, 2))
                     + 2 * sum(f(index) for index in range(2, divisions, 2)))


def _integral_curve(expr: sp.Expr, x: sp.Symbol, lower: sp.Rational, upper: sp.Rational,
                    divisions: int, rule: str) -> list[list[list[float]]]:
    width = float(upper - lower) / divisions
    segments: list[list[list[float]]] = []
    for index in range(divisions):
        x0, x1 = float(lower) + index * width, float(lower) + (index + 1) * width
        if rule == "trapezoid":
            y0 = _real_value(expr, x, sp.Rational(str(x0)))
            y1 = _real_value(expr, x, sp.Rational(str(x1)))
        else:
            y0 = _real_value(expr, x, sp.Rational(str(x0)))
            y1 = y0
        if y0 is not None and y1 is not None:
            segments.append([[x0, 0.0], [x0, y0], [x1, y1], [x1, 0.0], [x0, 0.0]])
    return segments


def _integral_mode(parsed: LabExpression, x: sp.Symbol, lower: sp.Rational | None,
                   upper: sp.Rational | None, divisions: int, lo: sp.Rational,
                   hi: sp.Rational) -> dict[str, Any]:
    expr = parsed.parsed.expr
    try:
        primitive = sp.integrate(expr, x)
    except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
        raise core.Unverifiable("지원 범위에서 원시함수를 구하지 못했습니다.") from exc
    def valid_primitive(candidate):
        if candidate.has(sp.Integral, sp.I):
            return False
        residual = sp.simplify(sp.diff(candidate, x) - expr)
        if residual == 0:
            return True
        if isinstance(residual, sp.Piecewise):
            domain = _domain(parsed, x)
            return all(value == 0 or region.intersect(domain).is_empty is True
                       for value, region in residual.as_expr_set_pairs())
        return False

    real_primitive = primitive.replace(sp.log, lambda arg: sp.log(sp.Abs(arg)))
    if valid_primitive(real_primitive):
        primitive = real_primitive
    elif valid_primitive(primitive) and all(
            _domain(parsed, x).is_subset(_as_set(sp.Gt(term.args[0], 0))) is True
            for term in primitive.atoms(sp.log)):
        pass  # The original real logarithms are defined on the integrand's domain.
    else:
        primitive = None
    if primitive is None:
        raise core.Unverifiable("원시함수를 미분하여 원래 식과 일치함을 확인하지 못했습니다.")
    result = _base_result("ok")
    result["rows"].append(_row("부정적분", primitive))
    result["curves"].append(_curve("f(x)", expr, parsed, x, lo, hi))
    result["steps"].append(f"원시함수 F(x) = {primitive}; 각 연속 구간에서 적분 상수 C를 더합니다.")
    if lower is None and upper is None:
        result["curves"].append(_curve("F(x)", primitive, parsed, x, lo, hi))
        return result
    if lower is None or upper is None:
        raise ValueError("정적분은 lower와 upper를 함께 입력해야 합니다.")
    start, end = min(lower, upper), max(lower, upper)
    domain = _window_domain(parsed, x, start, end)
    interval = sp.Interval(start, end)
    if interval.is_subset(domain) is not True:
        raise core.Unverifiable("정적분 전체 구간에서 실수 함수가 정의되어야 합니다.")
    if start == end:
        result["rows"].extend((_row("정적분", sp.S.Zero), _row("기하학적 넓이", sp.S.Zero)))
        result["curves"].append({"label": "누적 적분", "segments": [[[float(start), 0.0]]]})
        result["steps"].append("같은 점에서 시작해 끝나는 구간의 적분은 0입니다.")
        return result
    try:
        exact = sp.simplify(sp.integrate(expr, (x, lower, upper)))
    except (NotImplementedError, ValueError, TypeError, RecursionError) as exc:
        raise core.Unverifiable("정적분의 정확한 값을 확정할 수 없습니다.") from exc
    if exact.has(sp.Integral, sp.zoo, sp.nan, sp.oo, -sp.oo, sp.I) or exact.is_real is False:
        raise core.Unverifiable("정적분이 유한한 실수로 수렴함을 확인할 수 없습니다.")
    result["rows"].append(_row("정적분", exact))
    approx_rules = (("직사각형 근사", "left"), ("중점 근사", "midpoint"),
                    ("사다리꼴 근사", "trapezoid"), ("Simpson 근사", "simpson"))
    exact_numeric = core.scalar(sp.N(exact, 16))
    for label, rule in approx_rules:
        value = _integral_value(expr, x, lower, upper, divisions, rule)
        result["rows"].append(_row(label, _numeric(value), "numeric"))
        result["rows"].append(_row(f"{label.replace(' 근사', '')} 오차",
                                   _numeric(abs(value - exact_numeric)), "numeric"))
    try:
        geometric = sp.integrate(sp.Abs(expr), (x, lower, upper))
        if geometric.has(sp.Integral, sp.zoo, sp.nan, sp.oo, -sp.oo, sp.I):
            raise ValueError("unevaluated")
        geometric_value = core.scalar(sp.N(geometric, 16))
    except (NotImplementedError, ValueError, TypeError, ArithmeticError, OverflowError):
        # Independent composite midpoint estimate of the unsigned area.
        geometric_value = _integral_value(sp.Abs(expr), x, lower, upper, divisions, "midpoint")
    result["rows"].append(_row("기하학적 넓이", _numeric(abs(geometric_value)), "numeric"))
    result["curves"].append({"label": "리만 합", "segments": _integral_curve(expr, x, lower,
                                                                    upper, divisions, "left")})
    result["curves"].append({"label": "사다리꼴", "segments": _integral_curve(expr, x, lower,
                                                                    upper, divisions, "trapezoid")})
    accumulation = sp.simplify(primitive - primitive.subs(x, lower))
    result["curves"].append({"label": "누적 적분", "segments": _curve_segments(
        accumulation, x, interval, start, end)})
    result["steps"].extend((f"정적분 = F({upper}) - F({lower}) = {exact}",
                            f"분할 수 n = {divisions}; 각 수치 근사는 별도 표기합니다.",
                            "부호 있는 적분과 기하학적 넓이를 별도로 표시합니다."))
    return result


def calculate_lab(data: Any) -> dict[str, Any]:
    """Calculate one validated Function or Calculus Lab request."""
    try:
        if not isinstance(data, dict):
            raise ValueError("계산 요청은 JSON 객체여야 합니다.")
        mode = data.get("mode")
        if mode not in {"function", "limit", "derivative", "integral"}:
            raise ValueError("지원하지 않는 Mathematics Lab 모드입니다.")
        params = _params(data.get("params", {}))
        parsed = _parse_expression(data.get("expression"), params)
        x = X
        lo = _number(data.get("lo"), "lo", -10)
        hi = _number(data.get("hi"), "hi", 10)
        if lo >= hi:
            raise ValueError("그래프 범위에서 lo가 hi보다 작아야 합니다.")
        step = _number(data.get("step"), "step", "0.1")
        if step <= 0:
            raise ValueError("step은 0보다 커야 합니다.")
        other = None
        if data.get("other") is not None:
            if mode != "function":
                raise ValueError("other 수식은 function 모드에서만 사용할 수 있습니다.")
            other = _parse_expression(data["other"], params)
        if mode == "function":
            point = None if data.get("point") is None else _number(data["point"], "point")
            return _function_mode(parsed, other, x, lo, hi, point)
        if mode == "limit":
            point = _number(data.get("point"), "point", 0)
            return _limit_mode(parsed, x, point, step, lo, hi)
        if mode == "derivative":
            point = None if data.get("point") is None else _number(data["point"], "point")
            return _derivative_mode(parsed, x, point, step, lo, hi)
        lower = None if data.get("lower") is None else _number(data["lower"], "lower")
        upper = None if data.get("upper") is None else _number(data["upper"], "upper")
        divisions_raw = data.get("divisions", 100)
        if isinstance(divisions_raw, bool) or not isinstance(divisions_raw, int) or not 1 <= divisions_raw <= MAX_DIVISIONS:
            raise ValueError(f"분할 수는 1부터 {MAX_DIVISIONS}까지의 정수여야 합니다.")
        return _integral_mode(parsed, x, lower, upper, divisions_raw, lo, hi)
    except core.Unverifiable as exc:
        return _base_result("unverifiable", str(exc))
    except (SyntaxError, ValueError, KeyError, TypeError, RecursionError) as exc:
        return _base_result("invalid", str(exc))
    except (NotImplementedError, ArithmeticError, OverflowError):
        return _base_result("unverifiable", "지원 범위에서 실수 해 또는 유한한 값을 확정할 수 없습니다.")
