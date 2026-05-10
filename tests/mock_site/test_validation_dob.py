"""Tests for `validate_dob`."""

from __future__ import annotations

from datetime import date

from kestrel.mock_site.validation import Err, Ok, validate_dob

REFERENCE = date(2026, 5, 10)


def test_aged_17_returns_ok() -> None:
    dob = date(2009, 5, 10)  # exactly 17 today.
    result = validate_dob(dob.isoformat(), today=REFERENCE)
    assert isinstance(result, Ok)
    assert result.value == dob


def test_aged_16_returns_too_young() -> None:
    dob = date(2009, 5, 11)  # not yet 17 today.
    result = validate_dob(dob.isoformat(), today=REFERENCE)
    assert isinstance(result, Err)
    assert result.error == "dob_too_young"


def test_aged_100_exact_returns_ok() -> None:
    dob = date(1926, 5, 10)
    result = validate_dob(dob.isoformat(), today=REFERENCE)
    assert isinstance(result, Ok)


def test_aged_101_returns_too_old() -> None:
    dob = date(1925, 1, 1)
    result = validate_dob(dob.isoformat(), today=REFERENCE)
    assert isinstance(result, Err)
    assert result.error == "dob_too_old"


def test_non_iso_format_returns_format_wrong() -> None:
    assert validate_dob("10/05/2009", today=REFERENCE).error == "dob_format_wrong"


def test_iso_with_extra_chars_returns_format_wrong() -> None:
    assert validate_dob("2009-05-10T00:00:00", today=REFERENCE).error == "dob_format_wrong"


def test_empty_returns_required() -> None:
    assert validate_dob("", today=REFERENCE).error == "dob_required"


def test_whitespace_only_returns_required() -> None:
    assert validate_dob("   ", today=REFERENCE).error == "dob_required"


def test_future_date_returns_in_future() -> None:
    future = date(2030, 1, 1)
    assert validate_dob(future.isoformat(), today=REFERENCE).error == "dob_in_future"


def test_default_today_uses_real_clock() -> None:
    # Just exercise the default branch; assert any Result without binding to current date.
    result = validate_dob("2000-01-01")
    assert isinstance(result, Ok)


def test_invalid_iso_month_returns_format_wrong() -> None:
    assert validate_dob("2009-13-01", today=REFERENCE).error == "dob_format_wrong"
