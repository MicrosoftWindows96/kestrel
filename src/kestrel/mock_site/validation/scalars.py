"""Scalar validators: integer ranges, enum membership, string length.

Error keys (closed):
- `int_range_format_wrong`, `int_range_below_min`, `int_range_above_max`
- `enum_required`, `enum_invalid_value`
- `string_required`, `string_length_too_short`, `string_length_too_long`
"""

from __future__ import annotations

from typing import Final

from kestrel.mock_site.validation.result import Err, Ok, Result

ERR_INT_FORMAT: Final[str] = "int_range_format_wrong"
ERR_INT_BELOW: Final[str] = "int_range_below_min"
ERR_INT_ABOVE: Final[str] = "int_range_above_max"

ERR_ENUM_REQUIRED: Final[str] = "enum_required"
ERR_ENUM_INVALID: Final[str] = "enum_invalid_value"

ERR_STRING_REQUIRED: Final[str] = "string_required"
ERR_STRING_SHORT: Final[str] = "string_length_too_short"
ERR_STRING_LONG: Final[str] = "string_length_too_long"


def validate_int_range(value: str | int, *, min: int, max: int) -> Result[int, str]:  # noqa: A002
    lo = min
    hi = max
    parsed: int
    if isinstance(value, bool):
        return Err(ERR_INT_FORMAT)
    if isinstance(value, int):
        parsed = value
    else:
        token = value.strip()
        if not token:
            return Err(ERR_INT_FORMAT)
        try:
            parsed = int(token)
        except ValueError:
            return Err(ERR_INT_FORMAT)
    if parsed < lo:
        return Err(ERR_INT_BELOW)
    if parsed > hi:
        return Err(ERR_INT_ABOVE)
    return Ok(parsed)


def validate_enum(value: str, *, allowed: frozenset[str]) -> Result[str, str]:
    if not value:
        return Err(ERR_ENUM_REQUIRED)
    if value not in allowed:
        return Err(ERR_ENUM_INVALID)
    return Ok(value)


def validate_string_length(value: str, *, min: int, max: int) -> Result[str, str]:  # noqa: A002
    lo = min
    hi = max
    if not value:
        return Err(ERR_STRING_REQUIRED)
    length = len(value)
    if length < lo:
        return Err(ERR_STRING_SHORT)
    if length > hi:
        return Err(ERR_STRING_LONG)
    return Ok(value)
