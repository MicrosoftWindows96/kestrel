"""Tests for `validate_postcode`."""

from __future__ import annotations

import pytest

from kestrel.mock_site.validation import Err, Ok, validate_postcode

KNOWN_GOOD = [
    "SW1A 1AA",
    "M1 1AE",
    "B33 8TH",
    "CR2 6XH",
    "DN55 1PT",
]

KNOWN_BAD: list[tuple[str, str]] = [
    ("Q1 2AB", "postcode_invalid_first_position"),
    ("VA1 2AB", "postcode_invalid_first_position"),
    ("X1 2AB", "postcode_invalid_first_position"),
    ("AI1 2AB", "postcode_invalid_second_position"),
    ("AJ1 2AB", "postcode_invalid_second_position"),
    ("AZ1 2AB", "postcode_invalid_second_position"),
    ("SW1A 1AC", "postcode_invalid_final"),
    ("SW1A 1AI", "postcode_invalid_final"),
    ("SW1A 1AK", "postcode_invalid_final"),
    ("SW1A 1AM", "postcode_invalid_final"),
    ("SW1A 1AO", "postcode_invalid_final"),
    ("SW1A 1AV", "postcode_invalid_final"),
    ("12345", "postcode_format_wrong"),
    ("LONDON", "postcode_format_wrong"),
]


@pytest.mark.parametrize("good", KNOWN_GOOD)
def test_known_good_returns_canonical_ok(good: str) -> None:
    result = validate_postcode(good)
    assert isinstance(result, Ok)
    assert result.value == good
    assert result.value == result.value.upper()
    assert "  " not in result.value


@pytest.mark.parametrize(("bad", "key"), KNOWN_BAD)
def test_known_bad_returns_err_with_expected_key(bad: str, key: str) -> None:
    result = validate_postcode(bad)
    assert isinstance(result, Err)
    assert result.error == key


def test_lowercase_canonicalizes_to_uppercase() -> None:
    result = validate_postcode("sw1a 1aa")
    assert isinstance(result, Ok)
    assert result.value == "SW1A 1AA"


def test_double_space_collapses_to_single() -> None:
    result = validate_postcode("SW1A  1AA")
    assert isinstance(result, Ok)
    assert result.value == "SW1A 1AA"


def test_missing_space_canonicalizes_to_spaced_form() -> None:
    # Royal-Mail postcodes are spelled with the outward / inward split. The
    # canonicalized form always carries a single space; concatenated input is
    # accepted and rewritten on the way out.
    result = validate_postcode("SW1A1AA")
    assert isinstance(result, Ok)
    assert result.value == "SW1A 1AA"


def test_outward_only_returns_format_wrong() -> None:
    # Plan section 13 drops the outward-only branch; no form step uses it.
    for raw in ("SW1A", "M1", "B33", "CR2"):
        assert validate_postcode(raw).error == "postcode_format_wrong", raw


def test_empty_string_returns_required() -> None:
    assert validate_postcode("").error == "postcode_required"


def test_whitespace_only_returns_required() -> None:
    assert validate_postcode("   ").error == "postcode_required"


def test_first_position_q_via_proper_format() -> None:
    # Build a syntactically valid postcode whose first letter is Q so the
    # excluded-letter rule fires before the format fallback would.
    result = validate_postcode("QV1 1AB")
    assert isinstance(result, Err)
    assert result.error == "postcode_invalid_first_position"


def test_result_round_trip_map_and_map_err() -> None:
    ok = validate_postcode("SW1A 1AA")
    mapped_ok = ok.map(str.lower)
    assert isinstance(mapped_ok, Ok)
    assert mapped_ok.value == "sw1a 1aa"

    err = validate_postcode("LONDON")
    mapped_err = err.map_err(lambda key: f"err::{key}")
    assert isinstance(mapped_err, Err)
    assert mapped_err.error == "err::postcode_format_wrong"
