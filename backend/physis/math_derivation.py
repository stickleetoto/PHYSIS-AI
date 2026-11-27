"""Short, inspectable differentiation steps for an already validated SymPy tree."""
import sympy as sp


def derivative_steps(expr, x):
    records = []

    def visit(term, depth):
        if depth > 2 or len(records) >= 5 or not term.has(x):
            return
        if term == x:
            return
        if term.is_Add:
            rule = "합의 법칙으로 각 항을 따로 미분한 뒤 더합니다."
        elif term.is_Mul:
            rule = "상수 인수를 밖으로 꺼냅니다." if len([a for a in term.args if a.has(x)]) == 1 else "곱의 법칙으로 인수 하나씩 미분한 항을 더합니다."
        elif term.is_Pow:
            rule = "거듭제곱의 지수를 앞으로 내리고 지수를 1 줄인 뒤 밑의 도함수를 곱합니다."
        elif term.func in (sp.sin,sp.cos,sp.tan,sp.exp,sp.log):
            rule = "합성함수의 바깥 함수를 미분하고 안쪽 함수의 도함수를 곱합니다."
        else:
            return
        for child in term.args:
            visit(child,depth+1)
        if len(records)<5:
            entry=f"{rule} d/dx({term}) = {sp.diff(term,x)}"
            if entry not in records:
                records.append(entry)
    visit(expr,0)
    return records or [f"기준 변수 x에 대해 미분합니다. d/dx({expr}) = {sp.diff(expr,x)}"]
