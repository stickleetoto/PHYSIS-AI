from math import sqrt
import pytest
from pydantic import ValidationError

from physis.math_lab_api import MatrixRequest, NumericRequest
from physis.math_matrices import matrices
from physis.math_numerics import calculate
from physis.math_ode import InitialValue, solve_ivp


def values(result):
    return {row["label"]:row["value"] for row in result["rows"]}


@pytest.mark.parametrize("rhs,status", [([3,6],"무한해"),([3,7],"해 없음")])
def test_rank_deficient_system(rhs,status):
    result = values(matrices({"a":[[1,2],[2,4]],"b":[[1],[0]],"rhs":rhs}))
    assert result["연립방정식 Ax=b"] == status
    assert result["행렬식"]=="0" and "존재하지" in result["역행렬"]
    assert result["계수 rank(A)"]=="1"


def test_exact_solution_transform_and_matrix_limits():
    result=matrices({"a":[[2,1],[0,3]],"b":[[1,0],[0,1]],"rhs":[5,3]})
    rows=values(result)
    assert rows["해집합"]=="{(2, 1)}" and rows["행렬식"]=="6"
    assert result["curves"][-1]["segments"][0][1] == [1,3]
    assert {row["value"] for row in result["rows"] if row["label"]=="고유값"}=={"2","3"}
    for arr in [[[0]*6],[[0],[0,1]],[[0]]*6]:
        with pytest.raises(ValidationError):
            MatrixRequest(a=arr,b=[[1]],rhs=[0])


def numeric(**kw):
    return calculate(NumericRequest(**{"expression":"x^2-2",**kw}).model_dump())


def test_root_algorithms_approximate_independent_reference_and_quadrature():
    result=numeric(reference=sqrt(2))
    rows=values(result)
    for method in ["이분","뉴턴","할선"]:
        assert "충족" in rows[method+"법"]
        assert float(rows[method+" 절대 오차"]) < 1e-6
    assert float(rows["중심차분"]) == pytest.approx(3)
    assert float(rows["합성 Simpson (16분할)"]) == pytest.approx(1/3)
    assert result["traces"][0]["segments"][0][-1][1] <= 1e-7


def test_failed_root_and_unusable_domain_do_not_report_success():
    rows=values(numeric(expression="x^2+1",lo=0,hi=1))
    assert "같은 부호" in rows["이분법"] and "0입니다" in rows["뉴턴법"]
    assert "한도" in values(numeric(iterations=1))["이분법"]
    assert numeric(expression="1/x",lo=-1,hi=1)["status"]=="unverifiable"


@pytest.mark.parametrize("settings,expected", [
    ({"model":"exponential", "coefficient":1, "duration":1}, 2.718281828459045),
    ({"model":"spring", "k":1, "duration":1.5707963267948966}, 0),
    ({"model":"damped", "k":1, "damping":2, "duration":1}, 0.7357588823428847),
])
def test_ivp_against_known_initial_value_solutions(settings,expected):
    out=solve_ivp(InitialValue(**settings))
    for curve in (out["curves"][0],out["curves"][2]):
        assert curve["segments"][0][-1][1] == pytest.approx(expected, abs=1e-7)
    assert out["field"]


def test_scalar_euler_recurrence_and_quadrature_refinement():
    out=solve_ivp(InitialValue(model="exponential",coefficient=-0.5,steps=6,duration=0.6))
    assert out["curves"][1]["segments"][0][2][1] == pytest.approx(0.95**2)
    quad=numeric(expression="x^2",lo=0,hi=1,divisions=8)["quadrature"]
    coarse,fine=quad[0]["segments"][0]
    assert coarse[0]==4 and fine[0]==8
    assert coarse[1]/fine[1] == pytest.approx(4)
