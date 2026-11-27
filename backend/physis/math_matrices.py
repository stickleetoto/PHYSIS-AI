"""Exact elementary row operations on validated, small decimal matrices."""
import sympy as sp


def _matrix(rows):
    # The schema supplies finite numbers only. Decimal text avoids binary-float artifacts.
    return sp.Matrix([[sp.Rational(str(n)) for n in row] for row in rows])


def eliminate(augmented, variables):
    m = augmented.copy()
    steps = []
    row = 0
    for col in range(variables):
        pivot = next((j for j in range(row, m.rows) if m[j, col] != 0), None)
        if pivot is None:
            continue
        if pivot != row:
            m.row_swap(row, pivot)
            steps.append(f"R{row+1} ↔ R{pivot+1}")
        divisor = m[row, col]
        if divisor != 1:
            m.row_op(row, lambda v, _: v/divisor)
            steps.append(f"R{row+1} ← R{row+1} / ({divisor})")
        for j in range(m.rows):
            if j == row or m[j, col] == 0:
                continue
            factor = m[j, col]
            m.row_op(j, lambda v, i: v - factor*m[row, i])
            steps.append(f"R{j+1} ← R{j+1} − ({factor}) R{row+1}")
        row += 1
        if row == m.rows:
            break
    return m, steps


def matrices(data):
    a, b = _matrix(data["a"]), _matrix(data["b"])
    rhs = _matrix([[n] for n in data["rhs"]])
    rows = []

    def exact(label, value):
        rows.append(dict(label=label, value=str(value), latex=sp.latex(value), kind="exact"))

    def note(label, value):
        rows.append(dict(label=label, value=value, kind="note"))

    if a.shape == b.shape:
        exact("A + B", a+b)
        exact("A − B", a-b)
    else:
        note("A ± B", "행과 열 개수가 모두 같아야 합니다.")
    if a.cols == b.rows:
        exact("AB", a*b)
    else:
        note("AB", "A의 열 수와 B의 행 수가 달라 곱할 수 없습니다.")
    exact("전치행렬", a.T)
    basis = a.columnspace()
    exact("계수 rank(A)", len(basis))
    note("열벡터의 선형독립", "독립" if len(basis) == a.cols else "종속")
    if basis:
        exact("열공간의 기저 (열별 표시)", sp.Matrix.hstack(*basis))
    else:
        note("열공간의 기저", "공집합 (영공간만 생성)")
    if a.is_square:
        det = a.det()
        exact("행렬식", det)
        if det:
            exact("역행렬", a.inv())
        else:
            note("역행렬", "행렬식이 0이어서 존재하지 않습니다.")
    else:
        note("행렬식·역행렬", "정사각행렬에만 정의됩니다.")
    rref, steps = eliminate(a.row_join(rhs), a.cols)
    exact("기약 행 사다리꼴 [A | b]", rref)
    solutions = sp.linsolve((a, rhs))
    if solutions is sp.EmptySet:
        note("연립방정식 Ax=b", "해 없음")
    else:
        note("연립방정식 Ax=b", "유일해" if len(basis) == a.cols else "무한해")
        exact("해집합", solutions)
    grid = []
    if a.shape == (2, 2):
        for val, _, eigenspace in a.eigenvects():
            exact("고유값", val)
            exact("고유공간 기저", sp.Matrix.hstack(*eigenspace))
        def transform(x, y):
            return [float(a[0,0]*x + a[0,1]*y), float(a[1,0]*x + a[1,1]*y)]
        lines = []
        original = []
        for j in range(-2, 3):
            for ends in [((j,-2),(j,2)), ((-2,j),(2,j))]:
                lines.append([transform(*p) for p in ends])
                original.append(ends)
        grid = [dict(label="원래 격자", segments=original), dict(label="변환 격자", segments=lines)]
        grid.extend(dict(label=label, segments=[[[0,0], transform(*p)]])
                    for label, p in [("A e₁",(1,0)),("A e₂",(0,1))])
    return dict(status="ok", rows=rows, curves=grid, steps=steps or ["이미 기약 행 사다리꼴입니다."])
