"""Date-of-birth validator (UK rules).

Accepts ISO `YYYY-MM-DD` only. Age bounds: 17 <= age <= 100.

Error keys (closed):
- `dob_required`
- `dob_format_wrong`
- `dob_in_future`
- `dob_too_young`
- `dob_too_old`
"""

from __future__ import annotations

from datetime import date
from typing import Final

from kestrel.mock_site.validation.result import Err, Ok, Result

MIN_AGE: Final[int] = 17
MAX_AGE: Final[int] = 100

ERR_REQUIRED: Final[str] = "dob_required"
ERR_FORMAT: Final[str] = "dob_format_wrong"
ERR_FUTURE: Final[str] = "dob_in_future"
ERR_TOO_YOUNG: Final[str] = "dob_too_young"
ERR_TOO_OLD: Final[str] = "dob_too_old"


def validate_dob(raw: str, *, today: date | None = None) -> Result[date, str]:
    if not raw or not raw.strip():
        return Err(ERR_REQUIRED)

    parsed = _parse_iso(raw.strip())
    if parsed is None:
        return Err(ERR_FORMAT)

    reference = today if today is not None else date.today()
    if parsed > reference:
        return Err(ERR_FUTURE)

    age = _age_at(parsed, reference)
    if age < MIN_AGE:
        return Err(ERR_TOO_YOUNG)
    if age > MAX_AGE:
        return Err(ERR_TOO_OLD)
    return Ok(parsed)


def _parse_iso(raw: str) -> date | None:
    if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _age_at(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
