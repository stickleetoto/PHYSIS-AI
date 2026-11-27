"""Bounded, real-valued classroom solvers operating on the validated symbolic model."""
from math import isfinite
from time import perf_counter

import sympy as sp

from .symbolic_core import Unverifiable, domain_for, parse, scalar, symbol


def calculate(data):
    try:
        return _calculate(data)
    except (ValueError, TypeError, ArithmeticError, NotImplementedError, RecursionError) as exc:
        return dict(status="unverifiable", detail=str(exc) if isinstance(exc, ValueError) else "이 조건에서 유한한 실수 계산을 확정할 수 없습니다.")


def _calculate(data):
    x = symbol("x")
    p = parse(data["expression"])
    if p.names - {x}:
        raise ValueError("수치해석 수식에서는 독립변수 x만 사용하세요.")
    lo, hi, h, tol = (data[k] for k in ("lo","hi","h","tolerance"))
    left, right = sp.Rational(str(lo)), sp.Rational(str(hi))
    domain = domain_for(p, x, "real")
    if sp.Interval(left,right).is_subset(domain) is not True:
        raise ValueError("닫힌 구간 전체에서 함수가 정의되는 범위를 선택하세요.")
    derivative = sp.diff(p.expr,x)

    def at(t):
        if not isfinite(t) or abs(t)>1e4:
            raise Unverifiable("반복값이 허용 범위를 벗어났습니다.")
        r = sp.Rational(str(t))
        if domain.contains(r) is not sp.true:
            raise Unverifiable("반복값이 수식의 정의역을 벗어났습니다.")
        return scalar(p.expr.subs(x,r))

    rows, steps, curves, traces = [], [], [], []
    def row(label,value,kind="numeric"):
        rows.append(dict(label=label,value=str(value),kind=kind))

    def solve(method):
        a,b = lo,hi
        z = a if method=="뉴턴" else b
        history = []
        start=perf_counter()
        status="반복 한도 도달"
        try:
            fa,fb=at(a),at(b)
            if method=="이분" and fa*fb>0:
                return None, [], "양 끝에서 같은 부호", (perf_counter()-start)*1000
            for _ in range(data["iterations"]):
                if method=="이분":
                    z=a if fa==0 else b if fb==0 else (a+b)/2
                fz=at(z)
                history.append([z,fz])
                if abs(fz)<=tol:
                    status="잔차 허용 오차 충족"
                    break
                if method=="이분":
                    if fa*fz<0:
                        b,fb=z,fz
                    else:
                        a,fa=z,fz
                elif method=="뉴턴":
                    r = sp.Rational(str(z))
                    # Differentiate from both sides at a cusp or real-domain endpoint.
                    endpoint = domain.boundary.contains(r) is sp.true
                    if (p.expr.has(sp.Abs) and derivative.has(sp.sign, sp.Heaviside)) or endpoint:
                        q = sp.Dummy("h", real=True)
                        ratio = (p.expr.subs(x,r+q)-p.expr.subs(x,r))/q
                        if (endpoint or
                                sp.limit(ratio,q,0,dir="-") != sp.limit(ratio,q,0,dir="+")):
                            raise Unverifiable("시작점 또는 반복점에서 양측 미분을 확인할 수 없습니다.")
                    slope=scalar(derivative.subs(x,r))
                    if slope==0:
                        raise Unverifiable("접선 기울기가 0입니다.")
                    z-=fz/slope
                else:
                    if fb==fa:
                        raise Unverifiable("할선 분모가 0입니다.")
                    new=b-fb*(b-a)/(fb-fa)
                    a,fa,b,fb=b,fb,new,at(new)
                    z=new
        except (Unverifiable, ArithmeticError, TypeError, ValueError) as exc:
            status=str(exc) if isinstance(exc,Unverifiable) else "유한한 실수 반복값을 얻지 못했습니다."
        root=history[-1][0] if history and status=="잔차 허용 오차 충족" else None
        return root,history,status,(perf_counter()-start)*1000

    for name in ("이분","뉴턴","할선"):
        root,history,status,ms=solve(name)
        row(name+"법",status,"note")
        row(name+" 추정·반복·시간",f"{root:.9g} · {len(history)}회 · {ms:.3f} ms" if root is not None else f"— · {len(history)}회 · {ms:.3f} ms")
        truth=data.get("reference")
        if root is not None and truth is not None:
            row(name+" 절대 오차",f"{abs(root-truth):.8g}")
            row(name+" 상대 오차",f"{abs(root-truth)/abs(truth):.8g}" if truth!=0 else "기준값이 0이어서 정의되지 않음")
        if history:
            curves.append(dict(label=name+" 반복점",segments=[[p] for p in history if lo<=p[0]<=hi]))
            traces.append(dict(label=name,segments=[[[j+1,abs(fz)] for j,(_,fz) in enumerate(history)]]))
    points=[[lo+(hi-lo)*i/80,at(lo+(hi-lo)*i/80)] for i in range(81)]
    curves.insert(0,dict(label="f(x)",segments=[points]))
    center=(lo+hi)/2
    if center-h>=lo and center+h<=hi:
        c,minus,plus=at(center),at(center-h),at(center+h)
        for name,value in [("전진",(plus-c)/h),("후진",(c-minus)/h),("중심",(plus-minus)/(2*h))]:
            row(name+"차분",f"{value:.9g}")
    else:
        row("차분","간격 h를 줄여 양쪽 표본이 구간 안에 들게 하세요.","note")
    n=data["divisions"]
    try:
        exact = sp.integrate(p.expr,(x,left,right))
        area = None if exact.has(sp.Integral) else scalar(exact)
    except (NotImplementedError, ArithmeticError, ValueError, TypeError):
        area = None
    errors={"합성 사다리꼴":[], "합성 Simpson":[]}
    for count in (2*(n//4), n):
        delta=(hi-lo)/count
        ys=[scalar(p.expr.subs(x,left+(right-left)*i/count)) for i in range(count+1)]
        trap=delta*(sum(ys)-(ys[0]+ys[-1])/2)
        simpson=delta/3*(ys[0]+ys[-1]+4*sum(ys[1:-1:2])+2*sum(ys[2:-1:2]))
        for name, value in [("합성 사다리꼴",trap),("합성 Simpson",simpson)]:
            if area is not None:
                errors[name].append([count,abs(value-area)])
            if count==n:
                row(f"{name} ({n}분할)",f"{value:.9g}")
                if area is not None:
                    row(name+" 절대 오차",f"{abs(value-area):.8g}")
                    row(name+" 상대 오차",f"{abs((value-area)/area):.8g}" if area else "기준값이 0이어서 정의되지 않음")
    if area is None:
        row("구적 오차","유한한 기호 기준 적분값을 확인하지 못했습니다.","note")
    else:
        rows.append(dict(label="기호 기준 정적분",value=str(exact),latex=sp.latex(exact),kind="exact"))
    quadrature=[dict(label=name,segments=[points]) for name,points in errors.items() if points]
    steps.extend(["이분법은 초기 구간, 뉴턴법은 왼쪽 끝, 할선법은 양 끝에서 시작합니다.",
        f"차분 기준점은 구간 중점 {center:g}, 간격 h={h:g}입니다. 각 반복에서 |f(x)|를 기록합니다.",
        "기준 근을 입력한 경우에만 그 값에 대한 절대·상대 오차를 표시합니다. 잔차와 근의 위치 오차는 다릅니다."])
    return dict(status="ok",rows=rows,curves=curves,traces=traces,quadrature=quadrature,steps=steps)
