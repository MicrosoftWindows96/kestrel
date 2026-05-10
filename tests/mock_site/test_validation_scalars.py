"""Tests for scalar validators."""

from __future__ import annotations

from kestrel.mock_site.validation import (
    Err,
    Ok,
    validate_enum,
    validate_int_range,
    validate_string_length,
)


def test_int_range_below_min() -> None:
    assert validate_int_range("4", min=5, max=10).error == "int_range_below_min"


def test_int_range_at_min() -> None:
    result = validate_int_range("5", min=5, max=10)
    assert isinstance(result, Ok)
    assert result.value == 5


def test_int_range_mid() -> None:
    result = validate_int_range("7", min=5, max=10)
    assert isinstance(result, Ok)


def test_int_range_at_max() -> None:
    result = validate_int_range("10", min=5, max=10)
    assert isinstance(result, Ok)


def test_int_range_above_max() -> None:
    assert validate_int_range("11", min=5, max=10).error == "int_range_above_max"


def test_int_range_non_numeric() -> None:
    assert validate_int_range("abc", min=0, max=10).error == "int_range_format_wrong"


def test_int_range_empty_string() -> None:
    assert validate_int_range("", min=0, max=10).error == "int_range_format_wrong"


def test_int_range_accepts_int_value() -> None:
    result = validate_int_range(7, min=0, max=10)
    assert isinstance(result, Ok)
    assert result.value == 7


def test_int_range_rejects_bool() -> None:
    # Booleans are ints in Python; explicit reject.
    assert validate_int_range(True, min=0, max=10).error == "int_range_format_wrong"


def test_enum_invalid_value() -> None:
    assert validate_enum("blue", allowed=frozenset({"red", "green"})).error == "enum_invalid_value"


def test_enum_required_on_empty() -> None:
    assert validate_enum("", allowed=frozenset({"red"})).error == "enum_required"


def test_enum_accepts_member() -> None:
    result = validate_enum("red", allowed=frozenset({"red", "green"}))
    assert isinstance(result, Ok)
    assert result.value == "red"


def test_string_length_too_short() -> None:
    assert validate_string_length("ab", min=3, max=10).error == "string_length_too_short"


def test_string_length_too_long() -> None:
    assert validate_string_length("a" * 11, min=3, max=10).error == "string_length_too_long"


def test_string_length_at_boundaries() -> None:
    assert isinstance(validate_string_length("abc", min=3, max=10), Ok)
    assert isinstance(validate_string_length("a" * 10, min=3, max=10), Ok)


def test_string_required_on_empty() -> None:
    assert validate_string_length("", min=0, max=10).error == "string_required"


def test_result_ok_unwrap_err_raises() -> None:
    result = validate_int_range("5", min=0, max=10)
    assert isinstance(result, Ok)
    try:
        result.unwrap_err()
    except ValueError:
        return
    raise AssertionError("Ok.unwrap_err() should have raised")


def test_result_err_unwrap_raises() -> None:
    result = validate_int_range("abc", min=0, max=10)
    assert isinstance(result, Err)
    try:
        result.unwrap()
    except ValueError:
        return
    raise AssertionError("Err.unwrap() should have raised")


def test_result_pattern_match_destructure() -> None:
    """Lock the documented `match Result: case Ok(x) | Err(e):` contract."""
    ok = validate_int_range("5", min=0, max=10)
    seen: tuple[str, object] | None = None
    match ok:
        case Ok(value):
            seen = ("ok", value)
        case Err(error):
            seen = ("err", error)
    assert seen == ("ok", 5)

    err = validate_int_range("oops", min=0, max=10)
    match err:
        case Ok(value):
            seen = ("ok", value)
        case Err(error):
            seen = ("err", error)
    assert seen == ("err", "int_range_format_wrong")
