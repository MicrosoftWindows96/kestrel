"""Validation primitives.

Pure functions returning `Result[T, str]`. Error keys are stable
contracts consumed by route handlers (section 06) and template error
messages.
"""

from __future__ import annotations

from kestrel.mock_site.validation.dob import validate_dob
from kestrel.mock_site.validation.postcode import validate_postcode
from kestrel.mock_site.validation.result import Err, Ok, Result
from kestrel.mock_site.validation.scalars import (
    validate_enum,
    validate_int_range,
    validate_string_length,
)
from kestrel.mock_site.validation.vrn import validate_vrn

__all__ = [
    "Err",
    "Ok",
    "Result",
    "validate_dob",
    "validate_enum",
    "validate_int_range",
    "validate_postcode",
    "validate_string_length",
    "validate_vrn",
]
