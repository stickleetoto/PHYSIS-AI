"""Cross-check the supported classroom examples against independently known values."""
from math import cos, exp, log, sin, sqrt
import pytest

from physis.math_lab_engine import calculate_lab


@pytest.mark.parametrize("expression,at,expected", [
    ("2*x+1",1,3), ("x^2-1",1,0), ("x^3+1",1,2), ("1/(x+2)",1,1/3),
    ("sqrt(x+1)",1,sqrt(2)), ("abs(x-1)",0,1), ("exp(x)",1,exp(1)), ("log(x+2)",0,log(2)),
    ("sin(x)",1,sin(1)), ("cos(x)",1,cos(1)), ("piecewise((x^2, x<0), (x+1, True))",0,1),
])
def test_curve_agrees_with_reference_at_endpoint(expression,at,expected):
    result=calculate_lab(dict(mode="function",expression=expression,lo=at,hi=at+1,point=at))
    assert result["status"]=="ok",result.get("detail")
    assert any(abs(point[0]-at)<1e-13 and point[1]==pytest.approx(expected)
               for segment in result["curves"][0]["segments"] for point in segment)


def test_asymptotes_provided_as_plot_geometry():
    rational=calculate_lab(dict(mode="function",expression="1/(x-1)",lo=-2,hi=2))
    assert rational["guides"]=={"vertical":[1.0],"horizontal":[0.0]}
    oblique=calculate_lab(dict(mode="function",expression="x+1/x",lo=-2,hi=2))
    line=next(c for c in oblique["curves"] if c["label"]=="사선점근선")
    assert line["segments"]==[[[-2,-2],[2,2]]]


def test_branch_local_domains_and_cusp_extrema():
    expr="piecewise((log(x), x<1), (2, True))"
    result=calculate_lab(dict(mode="function",expression=expr,lo=-1,hi=2,point=0))
    entries={r["label"]:r["value"] for r in result["rows"]}
    assert entries["f(0)"]=="정의되지 않음"
    assert all(x>0 for segment in result["curves"][0]["segments"] for x,y in segment)
    for term,label in [("piecewise((x, x<0), (-x, True))","극댓값"), ("abs(x)","극솟값")]:
        result=calculate_lab(dict(mode="function",expression=term,lo=-2,hi=2))
        assert next(r["value"] for r in result["rows"] if r["label"]==label)=="(0, 0)"


@pytest.mark.parametrize("end,expected,area", [(0,-8/3,8/3),(2,0,0)])
def test_oriented_integral_and_unsigned_area(end,expected,area):
    result=calculate_lab(dict(mode="integral",expression="x^2",lower=2,upper=end,divisions=8))
    assert result["status"]=="ok"
    values={r["label"]:r["value"] for r in result["rows"]}
    from fractions import Fraction
    assert float(Fraction(values["정적분"]))==pytest.approx(expected)
    assert float(values["기하학적 넓이"])==pytest.approx(area)
