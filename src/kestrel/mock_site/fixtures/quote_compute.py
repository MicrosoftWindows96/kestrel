"""Premium computation. Reproducible, persona-aware, IPT-applied.

Per plan section 15. The premium is derived from a deterministic hash
of the canonical FormState JSON plus a persona-specific seed offset and
the persona's addon catalog. IPT is applied to the pre-tax total at the
UK standard motor rate (12 percent) and the result is quantized to two
decimal places.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from kestrel.mock_site.state.models import FormState

IPT_RATE: Final[Decimal] = Decimal("0.12")
QUANT: Final[Decimal] = Decimal("0.01")
BASE_FLOOR: Final[Decimal] = Decimal(200)
BASE_SPAN: Final[int] = 2300

ADDON_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ADDON_PRICES: Final[dict[str, Decimal]] = {
    "breakdown": Decimal("32.50"),
    "legal_cover": Decimal("18.00"),
    "courtesy_car": Decimal("22.50"),
    "key_cover": Decimal("12.00"),
    "windscreen": Decimal("9.50"),
}


@dataclass(frozen=True, slots=True)
class AddonLine:
    name: str
    price: Decimal

    def __post_init__(self) -> None:
        if not ADDON_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(
                f"AddonLine.name must match {ADDON_NAME_PATTERN.pattern}; got {self.name!r}"
            )

    def __repr__(self) -> str:
        return f"<AddonLine name={self.name}>"


@dataclass(frozen=True, slots=True)
class Premium:
    base_premium: Decimal
    addons: tuple[AddonLine, ...]
    total_pre_tax: Decimal
    ipt: Decimal
    total: Decimal

    def __repr__(self) -> str:
        return "<Premium ...>"


@dataclass(frozen=True, slots=True)
class PersonaQuoteSpec:
    """Subset of `PersonaSpec` consumed by `compute_premium`.

    Carved out of the full `PersonaSpec` so that section 06 can wire the
    quote pipeline without depending on the persona content (sections
    09/10 own the full `PersonaSpec`).
    """

    premium_seed_offset: int
    addon_catalog: tuple[str, ...]


def canonical_state_json(state: FormState) -> str:
    """Stable canonical JSON for a `FormState`.

    Used both by `compute_premium` (to derive the deterministic base)
    and by section 11's golden-fixture assertions.
    """
    return json.dumps(
        state.model_dump(mode="json", exclude_none=True, by_alias=False),
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_premium(state: FormState, persona: PersonaQuoteSpec) -> Premium:
    canon = canonical_state_json(state)
    digest = hashlib.sha256(canon.encode("utf-8")).digest()
    base = (
        BASE_FLOOR
        + Decimal(int.from_bytes(digest[:8], "big") % BASE_SPAN)
        + Decimal(persona.premium_seed_offset)
    ).quantize(QUANT)

    addon_lines = tuple(
        AddonLine(name=name, price=_price_for(name).quantize(QUANT))
        for name in persona.addon_catalog
    )
    addon_total = sum((line.price for line in addon_lines), Decimal(0))
    pre_tax = (base + addon_total).quantize(QUANT)
    ipt = (pre_tax * IPT_RATE).quantize(QUANT)
    total = (pre_tax + ipt).quantize(QUANT)
    return Premium(
        base_premium=base,
        addons=addon_lines,
        total_pre_tax=pre_tax,
        ipt=ipt,
        total=total,
    )


def _price_for(name: str) -> Decimal:
    try:
        return ADDON_PRICES[name]
    except KeyError as exc:
        raise ValueError(f"unknown addon: {name!r}") from exc


__all__ = [
    "ADDON_NAME_PATTERN",
    "ADDON_PRICES",
    "BASE_FLOOR",
    "BASE_SPAN",
    "IPT_RATE",
    "QUANT",
    "AddonLine",
    "PersonaQuoteSpec",
    "Premium",
    "canonical_state_json",
    "compute_premium",
]
