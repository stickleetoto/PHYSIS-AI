from uuid import uuid4

import pytest
from physis.physics import SPECS, parse_dsl, simulate
from physis.schema import Patch
from physis.state import build


def test_full_dsl_round_trip():
    experiment = build(SPECS["free_fall"], uuid4(), Patch(values={"height": 4.905}))
    recovered = parse_dsl(experiment.model_dump(mode="json"))
    assert simulate(recovered).facts["arrival_time"] == pytest.approx(1)


@pytest.mark.parametrize("change", ["unit", "max", "model", "methods"])
def test_independent_engine_rejects_redefined_model_metadata(change):
    payload = build(SPECS["free_fall"], uuid4(), Patch()).model_dump(mode="json")
    if change in {"unit", "max"}:
        payload["variables"][0][change] = "lb" if change == "unit" else 300
    else:
        payload[change] = "arbitrary" if change == "model" else ["rk4"]
    with pytest.raises(ValueError):
        parse_dsl(payload)


def test_mutated_in_memory_inputs_are_checked_at_engine_boundary():
    exp = build(SPECS["free_fall"], uuid4(), Patch())
    exp.values["mass_a"] = -1
    with pytest.raises(ValueError):
        simulate(exp)
