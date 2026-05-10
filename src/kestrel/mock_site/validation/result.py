"""Local `Result[T, E]` sum type.

Two variants: `Ok(value)` and `Err(error)`. Frozen, slotted, generic via
PEP 695 type parameters (Python 3.12+). Round-trip laws:
- `Ok(x).map(f) == Ok(f(x))`
- `Err(e).map(f) == Err(e)`
- `Ok(x).map_err(f) == Ok(x)`
- `Err(e).map_err(f) == Err(f(e))`

Pattern-match against the variants directly:

    match validate_postcode(raw):
        case Ok(canonical):
            ...
        case Err(error_key):
            ...
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def map[U](self, fn: Callable[[T], U]) -> Ok[U]:
        return Ok(fn(self.value))

    def map_err[E, F](self, _fn: Callable[[E], F]) -> Ok[T]:
        return self

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> NoReturn:
        raise ValueError(f"unwrap_err on Ok({self.value!r})")


@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def map[T, U](self, _fn: Callable[[T], U]) -> Err[E]:
        return self

    def map_err[F](self, fn: Callable[[E], F]) -> Err[F]:
        return Err(fn(self.error))

    def unwrap(self) -> NoReturn:
        raise ValueError(f"unwrap on Err({self.error!r})")

    def unwrap_err(self) -> E:
        return self.error


type Result[T, E] = Ok[T] | Err[E]

__all__ = ["Err", "Ok", "Result"]
