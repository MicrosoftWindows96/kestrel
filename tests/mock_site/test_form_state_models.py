"""Tests for `FormState` and per-step pydantic v2 sub-models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from kestrel.mock_site.state.models import (
    AddressStep,
    FormState,
    VehicleStep,
    empty_to_none,
)


def test_form_state_constructs_with_all_steps_none() -> None:
    state = FormState()
    assert state.vehicle is None
    assert state.cover is None
    assert state.populated_steps() == []


def test_empty_string_converts_to_none() -> None:
    assert empty_to_none("") is None
    assert empty_to_none("   ") is None
    assert empty_to_none("foo") == "foo"


def test_empty_field_normalizes_to_none_via_validator() -> None:
    step = VehicleStep(
        vehicle_make="",
        vehicle_model="Astra",
        vehicle_year="",
        vehicle_value="",
        vehicle_fuel="",
        vehicle_transmission="",
    )
    assert step.vehicle_make is None
    assert step.vehicle_model == "Astra"
    assert step.vehicle_year is None


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        VehicleStep(vehicle_make="Vauxhall", surprise="x")  # type: ignore[call-arg]


def test_form_state_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        FormState.model_validate({"vehicle": None, "surprise": {}})


def test_populated_steps_lists_step_names_in_url_form() -> None:
    state = FormState(
        vehicle=VehicleStep(vehicle_make="Vauxhall"),
        address=AddressStep(address_postcode="SW1A 1AA"),
    )
    assert state.populated_steps() == ["vehicle", "address"]


def test_repr_redacts_field_values() -> None:
    state = FormState(vehicle=VehicleStep(vehicle_make="Vauxhall"))
    rendered = repr(state)
    assert "Vauxhall" not in rendered
    assert "vehicle" in rendered
    assert rendered.startswith("<FormState steps=")


def test_canonical_dump_is_stable_across_calls() -> None:
    state = FormState(
        vehicle=VehicleStep(vehicle_make="Vauxhall", vehicle_model="Astra"),
    )
    canonical_a = json.dumps(
        state.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    canonical_b = json.dumps(
        state.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert canonical_a == canonical_b


def test_model_rebuild_idempotent() -> None:
    FormState.model_rebuild(force=True)
    FormState.model_rebuild(force=True)
    assert FormState().populated_steps() == []
