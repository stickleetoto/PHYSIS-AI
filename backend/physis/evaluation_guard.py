"""Let an explicit evaluation reserve each outbound generation against its own budget."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_reservation: ContextVar[Callable[[str], None] | None] = ContextVar("evaluation_reservation", default=None)


@contextmanager
def generation_guard(reserve_call: Callable[[str], None]) -> Iterator[None]:
    token = _reservation.set(reserve_call)
    try:
        yield
    finally:
        _reservation.reset(token)


def reserve_generation(operation: str) -> None:
    reserve = _reservation.get()
    if reserve is not None:
        reserve(operation)
