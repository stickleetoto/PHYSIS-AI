import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from physis import math_router as router
from physis.symbolic_core import calculate
from test_physics_core import experiment


def solve(op,expr,**kw):
    return calculate(dict(operation=op,expression=expr,**kw))


def test_algebra_and_calculus():
    assert solve("simplify","(x+1)^2-x^2")["result"]=="2*x + 1"
    assert solve("differentiate","x^3")["result"]=="3*x**2"
    assert solve("integrate","2*x")["result"]=="x**2"
    assert solve("integrate","1/x")["result"]=="log(Abs(x))"
    assert solve("substitute","x^2+2",values={"x":3})["result"]=="11"
    assert solve("solve","x^2",other="4",domain="positive")["result"]=="{2}"
    assert solve("solve","(x^2-1)/(x-1)",other="2")["result"]=="EmptySet"
    assert solve("differentiate","sqrt(x)")["domain"]=="Interval.open(0, oo)"


def test_domain_preservation_and_uncertainty():
    assert solve("equivalent","x/x",other="1")["status"]=="domain_mismatch"
    assert solve("equivalent","x/x",other="1",domain="positive")["status"]=="verified"
    assert solve("equivalent","sqrt(x)^2",other="x")["status"]=="domain_mismatch"
    assert solve("equivalent","sqrt(x^2)",other="x")["status"]=="failed"
    assert solve("equivalent","sqrt(x^2)",other="x",domain="nonnegative")["status"]=="verified"
    assert solve("equivalent","x+1",other="1+x",other_domain="positive")["status"]=="domain_mismatch"
    assert solve("simplify","x/x")["domain"]!="Reals"
    assert solve("substitute","x/x",values={"x":0})["status"]=="unverifiable"
    assert solve("substitute","1",values={"x":1})["status"]=="invalid"
    assert solve("equivalent","sqrt(x-y)",other="sqrt(y-x)")["status"]=="unverifiable"
    assert solve("compare","1/x",lower=-1,upper=1)["status"]=="unverifiable"
    assert solve("solve","cos(x)",other="x")["status"]=="unverifiable"


def test_dimension_and_graph_numeric_comparison():
    assert solve("dimension","F/m",other="a",units={"F":"N","m":"kg","a":"m/s²"})["status"]=="verified"
    assert solve("dimension","m+t",units={"m":"kg","t":"s"})["status"]=="failed"
    assert solve("dimension","sin(t)",units={"t":"s"})["status"]=="failed"
    assert solve("dimension","sin(f*t)",units={"t":"s","f":"Hz"})["result"]=="1"
    assert solve("dimension","p*V",units={"V":"m³"})["status"]=="unverifiable"
    graph = solve("graph","1/(x-0.1)",lower=-1,upper=1)
    assert len(graph["segments"])==2
    assert graph["segments"][0][-1][0]<.1<graph["segments"][1][0][0]
    comparison = solve("compare","x^2",lower=0,upper=1)
    assert comparison["result"]=="1/3"
    assert comparison["numeric"]>comparison["symbolic_value"]
    assert 0<comparison["absolute_error"]<.001
    root = solve("compare_root","x^2",other="2",lower=0,upper=2)
    assert root["result"]=="sqrt(2)" and root["absolute_error"]<1e-10
    assert solve("compare_root","x^2",other="2",lower=-2,upper=2)["status"]=="unverifiable"
    assert solve("compare_root","1/x",other="2",lower=-1,upper=1)["status"]=="unverifiable"


@pytest.mark.parametrize("text",["x.y","a[0]","unknown(x)","x^z","(x^8)^8","exp(exp(x))","2^100",
                                 "1.0000000000000001","1e-99999","sin(x,2)","x+"*90+"x"])
def test_grammar_and_complexity_limits(text):
    assert solve("simplify",text)["status"]=="invalid"


def test_router_worker_and_schema():
    app = FastAPI()
    app.include_router(router.router)
    with TestClient(app) as client:
        assert len(client.get("/api/formulas",params={"model":"pendulum"}).json()["items"])==3
        assert client.get("/api/formulas/missing").status_code==404
        assert client.get("/api/formulas/newton").json()["source"]["section"]=="5.3"
        result = client.post("/api/math",json={"operation":"differentiate","expression":"x^3"})
        assert result.json().get("result")=="3*x**2",result.json()
        assert client.post("/api/math",json={"operation":"graph","expression":"x"*181}).status_code==422


def test_worker_timeout_is_explicit_and_releases_capacity(monkeypatch):
    def timed_out(*args,**kw):
        assert kw["timeout"]>0
        raise subprocess.TimeoutExpired("worker",kw["timeout"])
    monkeypatch.setattr(router.subprocess,"run",timed_out)
    for _ in range(3):
        result = router.bounded_calculate({"operation":"simplify","expression":"x"})
        assert result["status"]=="unverifiable" and "시간" in result["detail"]


def test_verified_formula_claim_checks_expression_names_units_and_actual_conditions():
    exp = experiment("newton")
    units = {"a":"m/s²","F":"N","m":"kg"}
    ok = router.check_formula_claim("newton",exp,"F*m^(-1)",units)
    assert ok["expression_check"]["status"]==ok["units_check"]["status"]=="verified",ok
    assert ok["status"]=="applicable"
    assert router.check_formula_claim("newton",exp,"F*m")["status"]=="failed"
    assert router.check_formula_claim("newton",exp,"z/m")["status"]=="failed"
    assert router.check_formula_claim("newton",exp,"F/m",units|{"F":"kg"})["status"]=="failed"
    assert router.check_formula_claim("pendulum_small_angle",experiment("pendulum",angle=.8),
                                     "2*pi*sqrt(L/g)")["status"]=="outside_conditions"
