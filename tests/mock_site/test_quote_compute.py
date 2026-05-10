"""Premium computation contract: determinism, IPT, persona offsets.

Plan section 15 pins ``compute_premium`` as a pure function of
``(FormState, PersonaQuoteSpec)`` returning a Decimal-quantized
total. The 5 input x 3 persona golden-fixture table from plan
section 24.3 lands in section 11 as inline expected values; if the
table needs to diverge from the live algorithm the test fails
loudly so a downstream split notices.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from kestrel.mock_site.config import Persona
from kestrel.mock_site.fixtures.personas import build_persona_spec
from kestrel.mock_site.fixtures.quote_compute import (
    IPT_RATE,
    QUANT,
    PersonaQuoteSpec,
    compute_premium,
)
from kestrel.mock_site.state.models import (
    AddressStep,
    CoverStep,
    Driver1HistoryStep,
    Driver1Step,
    FormState,
    MileageStep,
    ParkingStep,
    VehicleModsStep,
    VehicleStep,
)


def _state_a() -> FormState:
    return FormState(
        vehicle=VehicleStep(
            vehicle_make="Vauxhall",
            vehicle_model="Astra",
            vehicle_year=2018,
            vehicle_value=8500,
            vehicle_fuel="petrol",
            vehicle_transmission="manual",
        ),
        vehicle_mods=VehicleModsStep(vehicle_mods=["none"]),
        parking=ParkingStep(parking_overnight="driveway", parking_daytime="street"),
        mileage=MileageStep(annual_mileage=8000, business_use="none"),
        driver_1=Driver1Step(
            driver_1_forename="Alex",
            driver_1_surname="Smith",
            driver_1_dob="1990-04-01",
            driver_1_licence_type="full_uk",
            driver_1_licence_held_since="2010-04-01",
            driver_1_occupation="engineer",
            driver_1_employment="employed",
        ),
        driver_1_history=Driver1HistoryStep(
            driver_1_claims="[]", driver_1_convictions="[]"
        ),
        address=AddressStep(
            address_postcode="SW1A 1AA",
            address_line_1="1 Example Street",
            address_town="Test Town",
        ),
        cover=CoverStep(
            cover_type="fully_comp",
            voluntary_excess=Decimal("250"),
            ncb_years=5,
            ncb_protection=False,
            addons=["breakdown"],
        ),
    )


def _state_b() -> FormState:
    state = _state_a()
    return state.model_copy(
        update={
            "vehicle": state.vehicle.model_copy(
                update={"vehicle_make": "Ford", "vehicle_value": 12500}
            ),
            "mileage": MileageStep(annual_mileage=20000, business_use="class_1"),
        }
    )


def _state_c() -> FormState:
    state = _state_a()
    return state.model_copy(
        update={
            "vehicle": state.vehicle.model_copy(
                update={"vehicle_year": 2010, "vehicle_value": 2200}
            ),
        }
    )


def _state_d() -> FormState:
    state = _state_a()
    return state.model_copy(
        update={
            "cover": CoverStep(
                cover_type="third_party_only",
                voluntary_excess=Decimal("500"),
                ncb_years=0,
                ncb_protection=False,
                addons=[],
            ),
        }
    )


def _state_e() -> FormState:
    state = _state_a()
    return state.model_copy(
        update={
            "vehicle_mods": VehicleModsStep(vehicle_mods=["alloy_wheels", "exhaust"]),
        }
    )


_STATES = {
    "s1": _state_a,
    "s2": _state_b,
    "s3": _state_c,
    "s4": _state_d,
    "s5": _state_e,
}

_PERSONAS = [Persona.A, Persona.B, Persona.C]


def _spec_for(persona: Persona) -> PersonaQuoteSpec:
    persona_spec = build_persona_spec(persona)
    return PersonaQuoteSpec(
        premium_seed_offset=persona_spec.premium_seed_offset,
        addon_catalog=persona_spec.addon_catalog,
    )


def test_ipt_rate_is_twelve_percent() -> None:
    assert Decimal("0.12") == IPT_RATE


def test_quant_is_two_decimals() -> None:
    assert Decimal("0.01") == QUANT


@pytest.mark.parametrize("state_key", list(_STATES))
@pytest.mark.parametrize("persona", _PERSONAS)
def test_compute_premium_is_deterministic(state_key: str, persona: Persona) -> None:
    state = _STATES[state_key]()
    spec = _spec_for(persona)
    first = compute_premium(state, spec)
    second = compute_premium(state, spec)
    assert first.total == second.total
    assert [(a.name, a.price) for a in first.addons] == [
        (a.name, a.price) for a in second.addons
    ]


@pytest.mark.parametrize("state_key", list(_STATES))
def test_persona_offsets_diverge_totals(state_key: str) -> None:
    state = _STATES[state_key]()
    totals = {persona: compute_premium(state, _spec_for(persona)).total for persona in _PERSONAS}
    # Three distinct persona offsets (0, 175, 350) must produce three
    # distinct totals on the same state.
    assert len(set(totals.values())) == 3, totals


@pytest.mark.parametrize("state_key", list(_STATES))
@pytest.mark.parametrize("persona", _PERSONAS)
def test_total_is_quantized_to_two_decimals(state_key: str, persona: Persona) -> None:
    state = _STATES[state_key]()
    premium = compute_premium(state, _spec_for(persona))
    # Decimal quantize to .01 means the exponent equals -2.
    assert premium.total.as_tuple().exponent == -2


_GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_premiums.json"


def _load_golden() -> dict[str, dict[str, str]]:
    return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("state_key", list(_STATES))
@pytest.mark.parametrize("persona", _PERSONAS)
def test_golden_premium_matches_committed_fixture(
    state_key: str, persona: Persona
) -> None:
    """Regression lock: 5 inputs x 3 personas pinned to fixtures/golden_premiums.json.

    Any algorithm or persona-offset drift trips this assertion. To
    intentionally accept a change, regenerate the JSON via the helper
    script (`scripts/generate_golden_premiums.py`) and commit the diff.
    """
    expected_by_persona = _load_golden()[state_key]
    expected = Decimal(expected_by_persona[persona.value])
    state = _STATES[state_key]()
    actual = compute_premium(state, _spec_for(persona)).total
    assert actual == expected, (
        f"{state_key}/{persona.value}: expected {expected}, got {actual}"
    )


def test_golden_fixture_shape() -> None:
    """The committed JSON file must carry exactly 5 states x 3 personas."""
    golden = _load_golden()
    assert set(golden) == {"s1", "s2", "s3", "s4", "s5"}
    for state_key, by_persona in golden.items():
        assert set(by_persona) == {"persona_a", "persona_b", "persona_c"}, state_key
        for persona_key, total_str in by_persona.items():
            total = Decimal(total_str)
            assert total > Decimal("0"), f"{state_key}/{persona_key}: {total_str}"
            assert total.as_tuple().exponent == -2
