import pytest
from pydantic import ValidationError
from physis.schema import Patch, Variable


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1.0"])
def test_inputs_are_finite_si_numbers(value):
    with pytest.raises(ValidationError):
        Patch(values={"mass": value})


def test_only_declared_operations():
    with pytest.raises(ValidationError):
        Patch(status="VERIFIED")


def test_invalid_physical_domain():
    with pytest.raises(ValidationError):
        Variable(key="m", label="질량", unit="kg", min=1, max=2, default=0, step=.1)
