"""UK postcode validator (Royal Mail rules).

Returns `Result[str, str]` where the success value is the canonicalized
postcode (uppercase, single space between outward and inward) and the
error value is one of the closed-set keys below. Outward-only postcodes
are rejected per plan §13 (no form step accepts the outward-only form).

Error keys (closed):
- `postcode_required`
- `postcode_format_wrong`
- `postcode_invalid_first_position`
- `postcode_invalid_second_position`
- `postcode_invalid_final`
"""

from __future__ import annotations

import re
from typing import Final

from kestrel.mock_site.validation.result import Err, Ok, Result

_FORMAT_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^([A-Z]{1,2})([0-9])([A-Z0-9]?) ?([0-9])([A-Z]{2})$"
)
_FIRST_EXCLUDED: Final[frozenset[str]] = frozenset({"Q", "V", "X"})
_SECOND_LETTER_EXCLUDED: Final[frozenset[str]] = frozenset({"I", "J", "Z"})
_FINAL_EXCLUDED: Final[frozenset[str]] = frozenset({"C", "I", "K", "M", "O", "V"})

ERR_REQUIRED: Final[str] = "postcode_required"
ERR_FORMAT: Final[str] = "postcode_format_wrong"
ERR_FIRST: Final[str] = "postcode_invalid_first_position"
ERR_SECOND: Final[str] = "postcode_invalid_second_position"
ERR_FINAL: Final[str] = "postcode_invalid_final"


def validate_postcode(raw: str) -> Result[str, str]:
    if not raw or not raw.strip():
        return Err(ERR_REQUIRED)

    compact = " ".join(raw.upper().split())
    match = _FORMAT_REGEX.fullmatch(compact)
    if match is None:
        return Err(ERR_FORMAT)

    outward_letters, digit, optional_third, final_digit, final_letters = match.groups()

    if outward_letters[0] in _FIRST_EXCLUDED:
        return Err(ERR_FIRST)
    if len(outward_letters) == 2 and outward_letters[1] in _SECOND_LETTER_EXCLUDED:
        return Err(ERR_SECOND)
    if any(letter in _FINAL_EXCLUDED for letter in final_letters):
        return Err(ERR_FINAL)

    canonical = f"{outward_letters}{digit}{optional_third or ''} {final_digit}{final_letters}"
    return Ok(canonical)
