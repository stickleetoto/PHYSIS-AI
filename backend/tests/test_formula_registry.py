from math import cos, sin

import pytest

from physis.formula_registry import (
    RECORDS, UNITS, check_applicability, formula_by_id, formula_for, formulas_for, search_formulas,
    verify_registered_formula,
)
from physis.physics import SPECS, simulate
from physis.symbolic_core import dimensional, parse
from test_physics_core import experiment


PARAMS = dict(h="height",g="g",x0="x0",v0="v0",a="a",m="mass",F="force",mu="mu",m1="mass_a",m2="mass_b",
              u1="v_a",u2="v_b",e="restitution",k="k",b="damping",L="length",theta0="angle",omega="omega",
              radius="radius",rho="density",depth="depth",p0="p0",V="volume",A1="area_in",A2="area_out",v1="speed_in",
              A="amplitude",f="frequency",lam="wavelength",phi="phase",n="moles",temp="temperature",Te="ambient",
              T0="initial_temp",rate="rate",Ta="temp_a",Tb="temp_b",Ca="capacity_a",Cb="capacity_b",G="conductance",
              edge="boundary_temp",amp="excess",diff="diffusivity",p1="inlet_pressure",flowv="speed")


@pytest.mark.parametrize("fid",[r["formula_id"] for r in RECORDS])
def test_registered_relation_against_engine(fid):
    r = formula_by_id(fid)
    model = r["model"]
    overrides = {
        "pendulum":{"angle":.2 if fid=="pendulum_small_angle" else -1.35,"length":1.6},
        "newton":{"force":-4,"mass":2.5},
        "circular":{"omega":-1.2},
        "damped":{"damping":1.5,"x0":-.7,"v0":.4},
        "friction":{"mu":.5,"v0":-3},
        "collision":{"restitution":.35},
        "spring":{"x0":.4,"mass":1.2},
        "acceleration":{"v0":-3.1,"a":1.6},
        "wave_superposition":{"phase":-.8},
        "cooling":{"initial_temp":252,"ambient":299},
        "heat_equilibrium":{"temp_a":265,"temp_b":327},
    }.get(model,{})
    setup = experiment(model, method="analytic", **overrides)
    run = simulate(setup)
    units = {v["name"]:v["unit"] for v in r["variables"]}
    assert dimensional(r["expression"],units,registry=True)==UNITS[units[r["lhs"]]]
    expression = parse(r["expression"],registry=True)
    assert {str(s) for s in expression.names}<=set(units)-{r["lhs"]}
    assert verify_registered_formula(fid,model,setup.values,units)["status"]=="verified"
    assert check_applicability(fid,setup)["status"]=="applicable"
    base = {name:setup.values[p] for name,p in PARAMS.items() if p in setup.values}
    base["R"] = 8.31446261815324
    count = 0
    for idx in (0,len(run.times)//3,len(run.times)-1):
        row = base|{"t":run.times[idx]}
        at = lambda key: run.series[key][idx]
        if fid in ("free_fall","uniform","acceleration","fluid_tracer"):
            observed = at("0.y" if model=="free_fall" else "0.x")
        elif fid in ("newton","damped"):
            row.update(x=at("0.x"),v=at("0.vx"))
            observed = at("0.ax")
        elif fid=="collision":
            observed = at("0.momentum")+at("1.momentum")
        elif fid=="collision_restitution":
            if row["t"]<run.facts["collision_time"]: continue
            observed = at("1.vx")-at("0.vx")
        elif fid=="friction":
            observed = run.facts["stop_distance"]
        elif fid in ("spring","pendulum","pendulum_small_angle"):
            observed = run.facts["reference_period"]
        elif fid=="pendulum_equation":
            row["theta"] = at("0.angle")
            observed = (at("0.ax")*cos(row["theta"])+at("0.ay")*sin(row["theta"]))/row["L"]
        elif fid=="circular":
            observed = (at("0.ax")**2+at("0.ay")**2)**.5
        elif fid.startswith("wave_"):
            # Test both non-identical spatial observation channels through the
            # same expression; the standing-wave origin alone is always zero.
            row["x"] = 0
            assert float(expression.expr.subs({s:row[str(s)] for s in expression.names}))==pytest.approx(at("0.displacement"),abs=2e-12)
            row["x"] = row["lam"]/4
            observed = at("0.quarter_displacement")
        elif fid=="heat_equilibrium":
            observed = run.facts["equilibrium_temp"]
        elif fid=="heat_exchange":
            observed = at("0.temperature")-at("1.temperature")
        elif fid=="heat_diffusion":
            row["x"] = 0
            assert float(expression.expr.subs({s:row[str(s)] for s in expression.names}))==pytest.approx(at("0.edge_temperature"))
            row["x"] = row["L"]/2
            observed = at("0.temperature")
        elif fid=="bernoulli":
            row["v2"] = at("1.speed")
            observed = at("1.pressure")
        else:
            observed = at({"hydrostatic":"0.pressure","buoyancy":"0.buoyancy","continuity":"1.speed",
                           "ideal_gas":"0.pressure","cooling":"0.temperature"}[fid])
        predicted = float(expression.expr.subs({s:row[str(s)] for s in expression.names}))
        assert predicted==pytest.approx(observed,abs=2e-11,rel=.0026 if fid=="pendulum_small_angle" else 2e-11)
        count += 1
    assert count>0


def test_complete_catalog_and_independent_conditions():
    assert {r["model"] for r in RECORDS}==set(SPECS)
    assert len({r["formula_id"] for r in RECORDS})==len(RECORDS)
    assert all(formula_for(k)["formula_id"]==k for k in SPECS)
    assert len(formulas_for("pendulum"))==3
    assert search_formulas("소각도","pendulum")[0]["formula_id"]=="pendulum_small_angle"
    assert search_formulas("없는 질의")==[] and formula_for("unknown") is None
    small = experiment("pendulum",angle=.2)
    large = experiment("pendulum",angle=.9)
    assert check_applicability("pendulum_small_angle",small)["status"]=="applicable"
    assert check_applicability("pendulum_small_angle",large)["status"]=="outside_conditions"
    assert check_applicability("pendulum",large)["status"]=="applicable"
    assert check_applicability("pendulum",experiment("pendulum",angle=0))["status"]=="outside_conditions"
    assert check_applicability("collision_restitution",experiment("collision",duration=.1))["status"]=="outside_conditions"
    assert check_applicability("friction",experiment("friction",mu=0))["status"]=="outside_conditions"
    wrong = large.model_dump()
    wrong["assumptions"] = []
    assert check_applicability("pendulum",wrong)["status"]=="unverifiable"
    assert verify_registered_formula("pendulum","pendulum",large.values,{"L":"kg"})["status"]=="failed"
    r = formula_for("spring")
    r["variables"].clear()
    assert formula_for("spring")["variables"]
