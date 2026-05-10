"""Form-state pydantic v2 models for the mock-site session store.

Composition (not tagged union): `FormState` carries one optional sub-model
per form step. Field names match the snake_case wire contract in plan
§23.2; the URL slug `additional-drivers` maps to the python attr
`additional_drivers` at the route layer.

Required-field error remapping returns closed-set keys such as
`vehicle_make_required`. Section 06 templates key off these strings.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def empty_to_none(v: object) -> object:
    """Convert empty / whitespace-only strings to None for optional fields."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


class _StepBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VehicleStep(_StepBase):
    vehicle_make: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    vehicle_model: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    vehicle_year: Annotated[int | None, BeforeValidator(empty_to_none)] = None
    vehicle_value: Annotated[int | None, BeforeValidator(empty_to_none)] = None
    vehicle_fuel: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    vehicle_transmission: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class VehicleModsStep(_StepBase):
    vehicle_mods: Annotated[list[str] | None, BeforeValidator(empty_to_none)] = None


class ParkingStep(_StepBase):
    parking_overnight: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    parking_daytime: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class MileageStep(_StepBase):
    annual_mileage: Annotated[int | None, BeforeValidator(empty_to_none)] = None
    business_use: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class Driver1Step(_StepBase):
    driver_1_forename: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_surname: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_dob: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_licence_type: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_licence_held_since: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_occupation: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_employment: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class Driver1HistoryStep(_StepBase):
    driver_1_claims: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    driver_1_convictions: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class AdditionalDriversStep(_StepBase):
    additional_driver_count: Annotated[int | None, BeforeValidator(empty_to_none)] = None


class AddressStep(_StepBase):
    address_postcode: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    address_line_1: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    address_town: Annotated[str | None, BeforeValidator(empty_to_none)] = None


class CoverStep(_StepBase):
    cover_type: Annotated[str | None, BeforeValidator(empty_to_none)] = None
    voluntary_excess: Annotated[int | None, BeforeValidator(empty_to_none)] = None
    ncb_years: Annotated[int | None, BeforeValidator(empty_to_none)] = None
    ncb_protection: Annotated[bool | None, BeforeValidator(empty_to_none)] = None
    addons: Annotated[list[str] | None, BeforeValidator(empty_to_none)] = None


class ReviewStep(_StepBase):
    pass


_STEP_FIELD_TO_NAME: dict[str, str] = {
    "vehicle": "vehicle",
    "vehicle_mods": "vehicle-mods",
    "parking": "parking",
    "mileage": "mileage",
    "driver_1": "driver-1",
    "driver_1_history": "driver-1-history",
    "additional_drivers": "additional-drivers",
    "address": "address",
    "cover": "cover",
    "review": "review",
}


class FormState(BaseModel):
    """Per-session form-step composition.

    Each step holds an optional sub-model. Empty form fields normalize to
    `None`; section 06 wires these into route handlers and populates step
    sub-models on each successful POST.
    """

    model_config = ConfigDict(extra="forbid")

    vehicle: VehicleStep | None = None
    vehicle_mods: VehicleModsStep | None = None
    parking: ParkingStep | None = None
    mileage: MileageStep | None = None
    driver_1: Driver1Step | None = None
    driver_1_history: Driver1HistoryStep | None = None
    additional_drivers: AdditionalDriversStep | None = None
    address: AddressStep | None = None
    cover: CoverStep | None = None
    review: ReviewStep | None = None

    def populated_steps(self) -> list[str]:
        return [
            _STEP_FIELD_TO_NAME[field_name]
            for field_name in self.__class__.model_fields
            if getattr(self, field_name) is not None
        ]

    def __repr__(self) -> str:
        return f"<FormState steps={self.populated_steps()}>"


__all__ = [
    "AdditionalDriversStep",
    "AddressStep",
    "CoverStep",
    "Driver1HistoryStep",
    "Driver1Step",
    "FormState",
    "MileageStep",
    "ParkingStep",
    "ReviewStep",
    "VehicleModsStep",
    "VehicleStep",
    "empty_to_none",
]
