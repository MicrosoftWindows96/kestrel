"""Tests for `validate_vrn`."""

from __future__ import annotations

import pytest

from kestrel.mock_site.validation import Err, Ok, validate_vrn

KNOWN_GOOD = [
    "AB12 CDE",
    "MK52 XYZ",
    "LD24 PRS",
    "EF73 JKL",
    "GH25 BCD",
]

KNOWN_BAD: list[tuple[str, str]] = [
    ("AB12 CDI", "vrn_suffix_excluded_letter"),
    ("AB12 CDQ", "vrn_suffix_excluded_letter"),
    ("IB12 CDE", "vrn_first_position_excluded"),
    ("QB12 CDE", "vrn_first_position_excluded"),
    ("ZB12 CDE", "vrn_first_position_excluded"),
    ("BI12 CDE", "vrn_first_position_excluded"),
    ("ABC123A", "vrn_older_format"),
    ("A123BCD", "vrn_older_format"),
    ("ABC123", "vrn_older_format"),
    ("12 ABCDE", "vrn_format_wrong"),
    ("ABCDE12", "vrn_format_wrong"),
]


@pytest.mark.parametrize("good", KNOWN_GOOD)
def test_known_good_returns_canonical_ok(good: str) -> None:
    result = validate_vrn(good)
    assert isinstance(result, Ok)
    assert result.value == good


@pytest.mark.parametrize(("bad", "key"), KNOWN_BAD)
def test_known_bad_returns_err_with_expected_key(bad: str, key: str) -> None:
    result = validate_vrn(bad)
    assert isinstance(result, Err)
    assert result.error == key


def test_lowercase_canonicalizes_to_uppercase() -> None:
    result = validate_vrn("ab12 cde")
    assert isinstance(result, Ok)
    assert result.value == "AB12 CDE"


def test_no_space_normalizes_to_space() -> None:
    result = validate_vrn("AB12CDE")
    assert isinstance(result, Ok)
    assert result.value == "AB12 CDE"


def test_empty_returns_required() -> None:
    assert validate_vrn("").error == "vrn_required"


def test_whitespace_only_returns_required() -> None:
    assert validate_vrn("   ").error == "vrn_required"
