"""UK VRN validator (DVLA current-format rules).

Returns `Result[str, str]` with the canonicalized VRN on success.

Error keys (closed):
- `vrn_required`
- `vrn_format_wrong`
- `vrn_first_position_excluded`
- `vrn_suffix_excluded_letter`
- `vrn_older_format`
"""

from __future__ import annotations

import re
from typing import Final

from kestrel.mock_site.validation.result import Err, Ok, Result

_CURRENT_REGEX: Final[re.Pattern[str]] = re.compile(r"^([A-Z]{2})([0-9]{2}) ?([A-Z]{3})$")
_OLDER_SUFFIX_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{3}[0-9]{1,3}[A-Z]$")
_OLDER_PREFIX_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z][0-9]{1,3}[A-Z]{3}$")
_OLDER_DATELESS_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{1,3}[0-9]{1,4}$")

_FIRST_PAIR_EXCLUDED: Final[frozenset[str]] = frozenset({"I", "Q", "Z"})
_SUFFIX_EXCLUDED: Final[frozenset[str]] = frozenset({"I", "Q"})

ERR_REQUIRED: Final[str] = "vrn_required"
ERR_FORMAT: Final[str] = "vrn_format_wrong"
ERR_FIRST: Final[str] = "vrn_first_position_excluded"
ERR_SUFFIX: Final[str] = "vrn_suffix_excluded_letter"
ERR_OLDER: Final[str] = "vrn_older_format"


def validate_vrn(raw: str) -> Result[str, str]:
    if not raw or not raw.strip():
        return Err(ERR_REQUIRED)

    canonical = _canonicalize(raw)
    match = _CURRENT_REGEX.fullmatch(canonical)
    if match is None:
        if _is_older_format(canonical):
            return Err(ERR_OLDER)
        return Err(ERR_FORMAT)

    first_pair, _digits, suffix = match.groups()
    if first_pair[0] in _FIRST_PAIR_EXCLUDED or first_pair[1] in _FIRST_PAIR_EXCLUDED:
        return Err(ERR_FIRST)
    if any(letter in _SUFFIX_EXCLUDED for letter in suffix):
        return Err(ERR_SUFFIX)
    return Ok(f"{first_pair}{_digits} {suffix}")


def _canonicalize(raw: str) -> str:
    parts = raw.upper().split()
    return " ".join(parts)


def _is_older_format(canonical: str) -> bool:
    compact = canonical.replace(" ", "")
    return any(
        pattern.fullmatch(compact)
        for pattern in (_OLDER_SUFFIX_REGEX, _OLDER_PREFIX_REGEX, _OLDER_DATELESS_REGEX)
    )
