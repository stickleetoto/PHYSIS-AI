"""Small real-expression language. Translate validated syntax nodes into math objects."""
import ast
from dataclasses import dataclass, field
from fractions import Fraction
import math
import re

import sympy as sp

from .symbolic_units import UNITS


class Unverifiable(ValueError):
    """A valid question exceeds the supported mathematics."""


class DimensionMismatch(ValueError):
    pass


FUNCTIONS = {"sin":sp.sin, "cos":sp.cos, "sqrt":sp.sqrt, "exp":sp.exp, "log":sp.log, "abs":sp.Abs}
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,15}\Z", re.ASCII)
ZERO = (0,0,0,0,0)


def symbol(name):
    if not isinstance(name,str) or not NAME.fullmatch(name) or name in {*FUNCTIONS, "pi", "elliptic_k"}:
        raise ValueError("변수는 영문자로 시작하는 16자 이내의 이름이어야 합니다.")
    return sp.Symbol(name, real=True)


def syntax(text):
    if not isinstance(text,str) or len(text)>180 or not re.fullmatch(r"[A-Za-z0-9_+*/^(). \t-]+",text):
        raise ValueError("허용된 숫자, 변수, 함수 및 산술 연산자로 수식을 입력하세요.")
    try:
        body = ast.parse(text.strip().replace("^","**"), mode="eval").body
    except (ValueError, SyntaxError, RecursionError) as exc:
        raise ValueError("수식의 괄호와 연산자를 확인하세요.") from exc
    if sum(1 for _ in ast.walk(body)) > 80:
        raise ValueError("수식은 최대 80개 구문 노드를 지원합니다.")
    return body


def exponent(node):
    sign = 1
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
        sign = -1 if isinstance(node.op,ast.USub) else 1
        node = node.operand
    if not isinstance(node,ast.Constant) or type(node.value) is not int or abs(node.value)>8:
        raise ValueError("거듭제곱의 지수는 −8부터 8까지의 정수만 지원합니다. 제곱근에는 sqrt를 사용하세요.")
    return sign*node.value


@dataclass
class Parsed:
    expr: sp.Expr
    guards: list = field(default_factory=list)
    names: set = field(default_factory=set)


def parse(text, *, registry=False):
    guards, names = [], set()
    funcs = FUNCTIONS | ({"elliptic_k":sp.elliptic_k} if registry else {})
    tree = syntax(text)
    normalized = text.strip().replace("^","**")

    def visit(n, depth=0, power_cost=1, nested_fn=0):
        if depth>16 or power_cost>24 or nested_fn>3:
            raise ValueError("수식의 중첩 또는 거듭제곱 복잡도 한도를 넘었습니다.")
        if isinstance(n,ast.Constant) and type(n.value) in (int,float):
            token = ast.get_source_segment(normalized,n)
            if not token or len(token)>20 or not re.fullmatch(r"(\d+(\.\d*)?|\.\d+)([eE][+-]?\d{1,2})?",token):
                raise ValueError("제한된 길이의 십진수만 입력하세요.")
            number = Fraction(token)
            if abs(number)>10**6:
                raise ValueError("수치 상수의 절댓값은 10⁶ 이하입니다.")
            if number.denominator>10**10:
                raise ValueError("수치 상수의 소수 자릿수를 줄이세요.")
            return sp.Rational(number.numerator,number.denominator)
        if isinstance(n,ast.Name):
            if n.id == "pi":
                return sp.pi
            variable = symbol(n.id)
            names.add(variable)
            if len(names)>12:
                raise ValueError("한 수식에서 지원하는 변수는 최대 12개입니다.")
            return variable
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            arg = visit(n.operand,depth+1,power_cost,nested_fn)
            return -arg if isinstance(n.op,ast.USub) else arg
        if isinstance(n,ast.BinOp):
            if isinstance(n.op,ast.Pow):
                p = exponent(n.right)
                base = visit(n.left,depth+1,power_cost*max(1,abs(p)),nested_fn)
                if p<=0:
                    guards.append(sp.Ne(base,0))
                return base**p
            left = visit(n.left,depth+1,power_cost,nested_fn)
            right = visit(n.right,depth+1,power_cost,nested_fn)
            if isinstance(n.op,ast.Add): return left+right
            if isinstance(n.op,ast.Sub): return left-right
            if isinstance(n.op,ast.Mult): return left*right
            if isinstance(n.op,ast.Div):
                guards.append(sp.Ne(right,0))
                return left/right
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in funcs and len(n.args)==1 and not n.keywords:
            name = n.func.id
            arg = visit(n.args[0],depth+1,power_cost,nested_fn+1)
            if name == "sqrt": guards.append(sp.Ge(arg,0))
            if name == "log": guards.append(sp.Gt(arg,0))
            if name == "elliptic_k": guards.append(sp.Lt(arg,1))
            if name=="exp" and (arg.has(sp.exp) or (arg.is_number and abs(arg)>40)):
                raise ValueError("지수함수의 상수 인자 범위 또는 중첩 한도를 넘었습니다.")
            return funcs[name](arg)
        raise ValueError("허용되지 않은 수식 문법입니다.")

    expr = visit(tree)
    if sp.false in guards or expr.has(sp.nan,sp.zoo,sp.oo,-sp.oo,sp.I):
        raise Unverifiable("실수 범위에서 정의되지 않은 연산입니다.")
    return Parsed(expr,[g for g in guards if g!=sp.true],names)


def dimensional(text, units, *, registry=False):
    parsed = parse(text,registry=registry)
    if any(str(s) not in units for s in parsed.names):
        raise Unverifiable("식에 나오는 각 변수의 SI 단위를 지정하세요.")
    def walk(n):
        if isinstance(n,ast.Constant): return ZERO
        if isinstance(n,ast.Name):
            if n.id=="pi": return ZERO
            if units[n.id] not in UNITS: raise Unverifiable("지원하는 SI 단위를 입력하세요.")
            return UNITS[units[n.id]]
        if isinstance(n,ast.UnaryOp): return walk(n.operand)
        if isinstance(n,ast.Call):
            dims = walk(n.args[0])
            if n.func.id=="abs": return dims
            if n.func.id=="sqrt": return tuple(Fraction(d,2) for d in dims)
            if dims!=ZERO: raise DimensionMismatch("이 함수의 인자는 무차원이어야 합니다.")
            return ZERO
        left = walk(n.left)
        if isinstance(n.op,ast.Pow): return tuple(d*exponent(n.right) for d in left)
        right = walk(n.right)
        if isinstance(n.op,(ast.Add,ast.Sub)):
            if left!=right: raise DimensionMismatch("더하거나 빼는 두 항의 차원이 다릅니다.")
            return left
        sign = -1 if isinstance(n.op,ast.Div) else 1
        return tuple(a+sign*b for a,b in zip(left,right))
    return walk(syntax(text))


DOMAINS = {"real":sp.S.Reals, "positive":sp.Interval.open(0,sp.oo), "nonnegative":sp.Interval(0,sp.oo),
           "nonzero":sp.Union(sp.Interval.open(-sp.oo,0),sp.Interval.open(0,sp.oo))}


def domain_for(p, x, scope):
    domain = DOMAINS[scope]
    for guard in p.guards:
        if guard.free_symbols-{x}:
            raise Unverifiable("다변수 식의 정의역 조건을 자동 판정할 수 없습니다. 매개변수를 먼저 대입하세요.")
        restriction = guard.as_set()
        if restriction.has(sp.ConditionSet):
            raise Unverifiable("정의역을 확정할 수 없습니다.")
        domain = domain.intersect(restriction)
    if domain == sp.S.EmptySet:
        raise Unverifiable("실수 정의역이 비어 있습니다.")
    return domain


def substitute(p, replacements):
    guards = [g.subs(replacements,simultaneous=True) for g in p.guards]
    if sp.false in guards:
        raise Unverifiable("대입값이 원래 수식의 정의역을 벗어났습니다.")
    expr = p.expr.subs(replacements,simultaneous=True)
    if expr.has(sp.nan,sp.zoo,sp.oo,-sp.oo,sp.I):
        raise Unverifiable("대입 결과가 유한한 실수가 아닙니다.")
    return Parsed(expr,[g for g in guards if g!=sp.true],p.names-replacements.keys())


def render(expr):
    if sp.count_ops(expr)>160:
        raise Unverifiable("결과가 표시 가능한 수식 복잡도를 넘었습니다.")
    label, latex = str(expr), sp.latex(expr)
    if max(len(label),len(latex))>2400:
        raise Unverifiable("결과가 표시 가능한 수식 길이를 넘었습니다.")
    return {"result":label,"latex":latex}


def scalar(expr):
    number = float(expr)
    if not math.isfinite(number):
        raise Unverifiable("유한한 실수 표본을 얻을 수 없습니다.")
    return number


def interval_samples(p, x, domain, lo, hi):
    window = domain.intersect(sp.Interval(lo,hi))
    if window.is_empty:
        raise Unverifiable("그래프 범위 안에 정의된 점이 없습니다.")
    segments = []
    for part in sp.Union.make_args(window):
        if isinstance(part,sp.FiniteSet):
            segments.extend([[[scalar(v),scalar(p.expr.subs(x,v))]] for v in part])
            continue
        if not isinstance(part,sp.Interval):
            raise Unverifiable("이 식의 연속 구간을 확정할 수 없습니다.")
        width = part.end-part.start
        points = []
        for i in range(81):
            if (i==0 and part.left_open) or (i==80 and part.right_open): continue
            value = part.start+width*sp.Rational(i,80)
            points.append([scalar(value),scalar(p.expr.subs(x,value))])
        if points: segments.append(points)
    return sorted(segments,key=lambda segment: segment[0][0])


def calculate(data):
    try:
        return _calculate(data)
    except DimensionMismatch as exc:
        return {"status":"failed","detail":str(exc)}
    except Unverifiable as exc:
        return {"status":"unverifiable","detail":str(exc)}
    except (NotImplementedError, ArithmeticError, TypeError, RecursionError):
        return {"status":"unverifiable","detail":"지원 범위 안에서 실수 해 또는 정의역을 확정할 수 없습니다."}
    except (SyntaxError, ValueError) as exc:
        return {"status":"invalid","detail":str(exc)}


def _calculate(data):
    op = data["operation"]
    x = symbol(data.get("variable","x"))
    left = parse(data["expression"])
    rhs_input = data.get("other")
    registry_claim = op=="registered_relation"
    right = parse(rhs_input,registry=registry_claim) if rhs_input else None
    if registry_claim:
        allowed = set(data["units"])-{data["lhs"]}
        if {str(s) for s in left.names}-allowed:
            return {"status":"failed","detail":"등록된 우변 변수 목록에 없는 이름입니다."}
        candidate_dim = dimensional(data["expression"],data["units"])
        if candidate_dim!=UNITS[data["units"][data["lhs"]]]:
            return {"status":"failed","detail":"주장한 식의 차원이 등록된 좌변과 다릅니다."}
        op = "equivalent"
    scope = data.get("domain","real")
    other_scope = data.get("other_domain") or scope
    base = {"status":"computed"}
    if op=="dimension":
        units = data.get("units") or {}
        left_dimension = dimensional(data["expression"],units)
        label = " ".join(f"{axis}^{power}" for axis,power in zip(("L","M","T","Θ","N"),left_dimension) if power) or "1"
        if right is None: return base|{"result":label}
        same = left_dimension==dimensional(rhs_input,units)
        return {"status":"verified" if same else "failed","result":label,"detail":"양변의 차원이 일치합니다." if same else "양변의 차원이 다릅니다."}
    values = data.get("values") or {}
    replacements = {symbol(name):sp.Rational(str(value)) for name,value in values.items()}
    if replacements.keys()-(left.names|(right.names if right else set())):
        raise ValueError("입력 수식에 없는 대입 변수가 있습니다.")
    if x in replacements:
        if op!="substitute": raise ValueError("연산의 기준 변수는 대입할 수 없습니다.")
        if DOMAINS[scope].contains(replacements[x])!=sp.true:
            raise Unverifiable("대입값이 선택한 정의역을 벗어났습니다.")
    left = substitute(left,replacements)
    if right: right = substitute(right,replacements)
    if op=="equivalent" and right:
        # Identical explicit restrictions remain provable even if they contain
        # several symbols. Otherwise compare actual real sets for the variable.
        conditions_same = set(left.guards)==set(right.guards) and scope==other_scope
        if not conditions_same:
            da, db = domain_for(left,x,scope), domain_for(right,x,other_scope)
            different = da.symmetric_difference(db).is_empty
            if different is None: raise Unverifiable("두 정의역의 일치 여부를 증명할 수 없습니다.")
            if not different:
                return {"status":"domain_mismatch","detail":"원래 두 식의 실수 정의역이 다릅니다.","domains":[str(da),str(db)]}
        if conditions_same and left.guards and set.union(*(g.free_symbols for g in left.guards))-{x}:
            # Identical guards prove identical domains. A concrete legal point
            # proves that domain is nonempty; the identity proof itself is symbolic.
            witness = None
            symbols = sorted(left.names|right.names|{x},key=str)
            for start in (1,2,3,-1):
                values = {v:sp.Integer(start+i) for i,v in enumerate(symbols)}
                if DOMAINS[scope].contains(values[x])==sp.true and all(
                        g.subs(values)==sp.true for g in left.guards):
                    witness = values
                    break
            if witness is not None:
                delta = sp.simplify(left.expr-right.expr)
                if delta==0:
                    return {"status":"verified","detail":"동일하고 비어 있지 않은 정의역에서 식의 차가 항등적으로 0입니다.",
                            "domain":", ".join(str(g) for g in left.guards)}
                if delta.subs(witness).is_zero is False:
                    return {"status":"failed","detail":"공통 정의역에서 두 수식의 값이 다른 점을 확인했습니다."}
            raise Unverifiable("다변수 정의역에서 항등성을 확정할 수 없습니다.")
        common = domain_for(left,x,scope)
        delta = sp.simplify(left.expr-right.expr)
        if common.is_subset(sp.Interval(0,sp.oo)) is True:
            delta = sp.refine(delta,sp.Q.nonnegative(x))
        if delta==0: return {"status":"verified","detail":"같은 정의역에서 두 표현의 차가 0입니다.","domain":str(common)}
        # A concrete admissible witness proves non-identity. No conclusion
        # follows from merely matching a finite sample.
        for point in [1,2,-1,0,sp.Rational(1,2),-2]:
            if common.contains(point)!=sp.true: continue
            value = sp.simplify(delta.subs(x,point))
            if value.is_number and value.is_zero is False:
                return {"status":"failed","detail":f"{x} = {point}에서 두 식의 값이 다릅니다."}
        raise Unverifiable("두 식의 동치 여부를 증명할 수 없습니다.")
    if op in ("solve","equivalent","compare_root") and not right:
        raise ValueError("두 번째 식을 입력하세요.")
    if op in ("graph","compare","compare_root","solve") and (left.names|(right.names if right else set()))-{x}:
        raise Unverifiable("한 변수만 남기고 나머지 매개변수를 대입하세요.")
    if op in ("simplify","substitute","differentiate","integrate") and any(g.free_symbols-{x} for g in left.guards):
        domain_text = str(DOMAINS[scope])+"; "+", ".join(str(g) for g in left.guards)
    else:
        domain_text = str(domain_for(left,x,scope))
    base["domain"] = domain_text
    if op in ("simplify","substitute"):
        return base|render(sp.simplify(left.expr))
    if op=="differentiate":
        if any(x in g.free_symbols and g.free_symbols-{x} for g in left.guards):
            raise Unverifiable("매개변수를 대입한 뒤 경계점에서의 미분 가능성을 확인하세요.")
        derivative = sp.diff(left.expr,x)
        if derivative.has(sp.Derivative,sp.sign,sp.DiracDelta) or left.expr.has(sp.Abs):
            raise Unverifiable("구간별 미분 및 경계점의 미분 가능성을 확정할 수 없습니다.")
        from sympy.calculus.util import continuous_domain
        if not any(g.free_symbols-{x} for g in left.guards):
            original_domain = domain_for(left,x,scope).interior
            if left.expr.free_symbols-{x}:
                if derivative.has(sp.Pow) and derivative!=left.expr and left.guards:
                    raise Unverifiable("매개변수를 대입한 뒤 미분 가능 구간을 확인하세요.")
            else:
                base["domain"] = str(original_domain.intersect(continuous_domain(derivative,x,sp.S.Reals)))
        return base|render(derivative)
    if op=="solve":
        domain = domain_for(left,x,scope).intersect(domain_for(right,x,other_scope))
        result = sp.solveset(left.expr-right.expr,x,domain=domain)
        if result.has(sp.ConditionSet): raise Unverifiable("실수 해집합을 확정할 수 없습니다.")
        return base|{"domain":str(domain)}|render(result)
    if op=="integrate":
        primitive = sp.integrate(left.expr,x)
        if primitive.has(sp.Integral,sp.Piecewise): raise Unverifiable("지원 범위에서 원시함수를 구하지 못했습니다.")
        if primitive.has(sp.log) and left.expr.free_symbols-{x}:
            raise Unverifiable("실수 로그의 구간을 정하려면 매개변수를 먼저 대입하세요.")
        if primitive.has(sp.log):
            primitive = primitive.replace(sp.log,lambda arg:sp.log(sp.Abs(arg)))
        if primitive.has(sp.I) or sp.simplify(sp.diff(primitive,x)-left.expr).equals(0) is not True:
            # abs in a real logarithm introduces sign; check on each open interval
            if not (left.expr==1/x and primitive==sp.log(sp.Abs(x))):
                raise Unverifiable("원시함수를 미분하여 원래 식을 확인할 수 없습니다.")
        return base|render(primitive)|{"detail":"각 연속 구간에서 적분 상수 C를 더합니다."}
    lo,hi = (sp.Rational(str(data.get(k,v))) for k,v in [("lower",-2),("upper",2)])
    if lo>=hi: raise ValueError("구간의 끝값이 시작값보다 커야 합니다.")
    domain = domain_for(left,x,scope)
    if op=="graph":
        return base|{"segments":interval_samples(left,x,domain,lo,hi)}
    if op=="compare_root":
        bracket = sp.Interval(lo,hi)
        domain = domain.intersect(domain_for(right,x,other_scope))
        if bracket.is_subset(domain) is not True:
            raise Unverifiable("이분법의 전체 구간에서 양변이 연속이어야 합니다.")
        residual = left.expr-right.expr
        roots = sp.solveset(residual,x,domain=bracket)
        if not isinstance(roots,sp.FiniteSet) or len(roots)!=1:
            raise Unverifiable("비교 구간 안에서 유일한 실수 해를 증명할 수 없습니다.")
        exact = next(iter(roots))
        a,b = lo,hi
        def sign_at(z):
            value = residual.subs(x,z)
            if value.is_zero is True: return 0
            if value.is_positive is True: return 1
            if value.is_negative is True: return -1
            raise Unverifiable("이분법에서 잔차의 부호를 확정할 수 없습니다.")
        fa,fb = sign_at(a),sign_at(b)
        if fa==fb and fa!=0:
            raise Unverifiable("양 끝에서 잔차 부호가 같아 이분법을 적용할 수 없습니다.")
        steps = 0
        midpoint = a if fa==0 else b
        if fa!=0 and fb!=0:
            for steps in range(1,41):
                midpoint = (a+b)/2
                fm = sign_at(midpoint)
                if fm==0: break
                if (fa<0)==(fm<0):
                    a,fa = midpoint,fm
                else:
                    b = midpoint
        numeric,exact_value = scalar(midpoint),scalar(exact)
        return base|render(exact)|{"domain":str(domain),"numeric":numeric,"symbolic_value":exact_value,
            "steps":steps,"method":"bisection","absolute_error":abs(numeric-exact_value)}
    if op=="compare":
        if sp.Interval(lo,hi).is_subset(domain) is not True:
            raise Unverifiable("비교 구간 전체에서 정의되는 연속 함수가 필요합니다.")
        exact = sp.integrate(left.expr,(x,lo,hi))
        if exact.has(sp.Integral): raise Unverifiable("비교할 기호 적분값을 결정할 수 없습니다.")
        # Composite trapezoidal rule with a fixed, disclosed sample grid.
        steps = 80
        dx = (hi-lo)/steps
        samples = [scalar(left.expr.subs(x,lo+i*dx)) for i in range(steps+1)]
        numeric = scalar(dx)*(.5*samples[0]+sum(samples[1:-1])+.5*samples[-1])
        exact_value = scalar(exact)
        return base|render(exact)|{"numeric":numeric,"symbolic_value":exact_value,"steps":steps,
            "method":"trapezoid","absolute_error":abs(numeric-exact_value)}
    raise ValueError("지원하지 않는 연산입니다.")
