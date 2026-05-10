"""Quote-form routes. Phase E: full ten-step surface for EASY + persona_a.

Sections 07 and 08 add the challenge gate and HARD-mode CSRF service.
Sections 09 and 10 add persona_b and persona_c full template trees;
this section preserves the section-03 persona_c htmx prototype contract
on the `vehicle` step so those tests stay green.
"""

from __future__ import annotations

import re
import secrets
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from starlette.datastructures import FormData

from kestrel.mock_site.config import Difficulty, Persona
from kestrel.mock_site.csrf import csrf_verify
from kestrel.mock_site.fixtures.quote_compute import (
    PersonaQuoteSpec,
    compute_premium,
)
from kestrel.mock_site.state.models import (
    AdditionalDriversStep,
    AddressStep,
    CoverStep,
    Driver1HistoryStep,
    Driver1Step,
    FormState,
    MileageStep,
    ParkingStep,
    ReviewStep,
    VehicleModsStep,
    VehicleStep,
)
from kestrel.mock_site.state.store import SessionStore, get_session_store
from kestrel.mock_site.validation import validate_dob, validate_postcode

SID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{43}$")
HX_RESWAP_HEADER: Final[str] = "HX-Reswap"
HX_RESWAP_VALUE: Final[str] = "outerHTML"
SESSION_COOKIE: Final[str] = "kestrel_session"
LIST_FIELDS: Final[frozenset[str]] = frozenset({"vehicle_mods", "addons"})

STEP_REQUIRED_FIELDS: Final[dict[str, frozenset[str]]] = {
    "vehicle": frozenset(
        {
            "vehicle_make",
            "vehicle_model",
            "vehicle_year",
            "vehicle_value",
            "vehicle_fuel",
            "vehicle_transmission",
        }
    ),
    "vehicle-mods": frozenset({"vehicle_mods"}),
    "parking": frozenset({"parking_overnight", "parking_daytime"}),
    "mileage": frozenset({"annual_mileage", "business_use"}),
    "driver-1": frozenset(
        {
            "driver_1_forename",
            "driver_1_surname",
            "driver_1_dob",
            "driver_1_licence_type",
            "driver_1_licence_held_since",
            "driver_1_occupation",
            "driver_1_employment",
        }
    ),
    "driver-1-history": frozenset({"driver_1_claims", "driver_1_convictions"}),
    "additional-drivers": frozenset({"additional_driver_count"}),
    "address": frozenset({"address_postcode", "address_line_1", "address_town"}),
    "cover": frozenset(
        {
            "cover_type",
            "voluntary_excess",
            "ncb_years",
            "ncb_protection",
        }
    ),
    "review": frozenset(),
}

# Map pydantic v2 error type identifiers to the closed-set field-error suffix
# §13 templates key off. Anything outside this map collapses to `_format_wrong`.
_PYDANTIC_KIND_TO_KEY_SUFFIX: Final[dict[str, str]] = {
    "missing": "required",
    "int_parsing": "format_wrong",
    "int_type": "format_wrong",
    "float_parsing": "format_wrong",
    "bool_parsing": "format_wrong",
    "bool_type": "format_wrong",
    "string_type": "format_wrong",
    "list_type": "format_wrong",
    "value_error": "format_wrong",
    "type_error": "format_wrong",
    "greater_than": "out_of_range",
    "greater_than_equal": "out_of_range",
    "less_than": "out_of_range",
    "less_than_equal": "out_of_range",
}

STEP_ORDER: Final[tuple[str, ...]] = (
    "vehicle",
    "vehicle-mods",
    "parking",
    "mileage",
    "driver-1",
    "driver-1-history",
    "additional-drivers",
    "address",
    "cover",
    "review",
)

# Step slug -> FormState attr.
STEP_TO_ATTR: Final[dict[str, str]] = {
    "vehicle": "vehicle",
    "vehicle-mods": "vehicle_mods",
    "parking": "parking",
    "mileage": "mileage",
    "driver-1": "driver_1",
    "driver-1-history": "driver_1_history",
    "additional-drivers": "additional_drivers",
    "address": "address",
    "cover": "cover",
    "review": "review",
}

# Step slug -> template filename.
STEP_TO_TEMPLATE: Final[dict[str, str]] = {
    "vehicle": "step_01_vehicle.html",
    "vehicle-mods": "step_02_vehicle_mods.html",
    "parking": "step_03_parking.html",
    "mileage": "step_04_mileage.html",
    "driver-1": "step_05_driver_1.html",
    "driver-1-history": "step_06_driver_1_history.html",
    "additional-drivers": "step_07_additional_drivers.html",
    "address": "step_08_address.html",
    "cover": "step_09_cover.html",
    "review": "step_10_review.html",
}

STEP_MODELS: Final[dict[str, type[Any]]] = {
    "vehicle": VehicleStep,
    "vehicle-mods": VehicleModsStep,
    "parking": ParkingStep,
    "mileage": MileageStep,
    "driver-1": Driver1Step,
    "driver-1-history": Driver1HistoryStep,
    "additional-drivers": AdditionalDriversStep,
    "address": AddressStep,
    "cover": CoverStep,
    "review": ReviewStep,
}

router = APIRouter(prefix="/quote", tags=["quote"])
_logger = structlog.get_logger("kestrel.mock_site.routes.quote")


@router.get("/start")
async def quote_start(
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> RedirectResponse:
    """Mint a fresh sid, persist an empty FormState, redirect to /vehicle."""
    sid = secrets.token_urlsafe(32)
    await store.put(sid, FormState())
    response = RedirectResponse(
        url=f"/quote/{sid}/vehicle",
        status_code=302,
    )
    # Secure=False is intentional: mock runs on http://127.0.0.1 only and
    # Secure=True would make the cookie undeliverable in tests.
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/quote",
    )
    return response


@router.post("/{sid}/submit")
async def submit(
    sid: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    _csrf: Annotated[None, Depends(csrf_verify)],
) -> HTMLResponse:
    _validate_sid_format(sid)
    _verify_sid_cookie_strict(request, sid)
    state = await _load_or_404(store, sid)
    if not _all_steps_complete(state):
        raise HTTPException(status_code=400, detail="state incomplete")

    return _render_quote_result(request, sid, state)


@router.get("/{sid}/{step}")
async def get_step(
    sid: str,
    step: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    back: int | None = None,
) -> Response:
    _validate_sid_format(sid)
    _validate_step_slug(step)
    settings = request.app.state.settings

    if settings.persona is Persona.C:
        return _persona_c_get_step(request, sid, step, settings.difficulty)

    _verify_sid_cookie_match(request, sid)
    state = await _load_or_404(store, sid)
    pointer_index = _logical_pointer(state)
    requested_index = STEP_ORDER.index(step)
    if back != 1 and requested_index > pointer_index:
        target = STEP_ORDER[pointer_index]
        return RedirectResponse(url=f"/quote/{sid}/{target}", status_code=302)

    return _render_step(request, sid, step, state, errors={})


@router.post("/{sid}/{step}")
async def post_step(
    sid: str,
    step: str,
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    _csrf: Annotated[None, Depends(csrf_verify)],
) -> Response:
    _validate_sid_format(sid)
    _validate_step_slug(step)
    _verify_sid_cookie_strict(request, sid)
    state = await _load_or_404(store, sid)

    form = await request.form()
    parsed_payload = _form_to_payload(step, form)
    parsed, errors = _parse_step_form(step, parsed_payload)
    if errors:
        return _render_step(request, sid, step, state, errors=errors, status_code=200)

    from_state = _logical_pointer_label(state)
    setattr(state, STEP_TO_ATTR[step], parsed)
    to_state = _logical_pointer_label(state)
    await store.put(sid, state)

    field_names: frozenset[str] = (
        frozenset(parsed_payload.keys()) if parsed is not None else frozenset()
    )
    _emit_state_transition(
        session_id=sid,
        from_state=from_state,
        to_state=to_state,
        step_name=step,
        field_names=field_names,
    )

    next_slug = _next_step(step)
    if step == "review" or next_slug is None:
        return _render_quote_result(request, sid, state)
    return RedirectResponse(url=f"/quote/{sid}/{next_slug}", status_code=302)


def _validate_sid_format(sid: str) -> None:
    if not SID_PATTERN.fullmatch(sid):
        raise HTTPException(status_code=400, detail="invalid sid format")


def _validate_step_slug(step: str) -> None:
    if step not in STEP_ORDER:
        raise HTTPException(status_code=404, detail=f"unknown step: {step}")


def _verify_sid_cookie_match(request: Request, sid: str) -> None:
    """GET-side cookie check: tolerates a missing cookie.

    The first GET after `/quote/start` redirect may arrive before the
    cookie is processed by some clients; only an explicit mismatch is a
    403 condition for GET requests.
    """
    cookie_sid = request.cookies.get(SESSION_COOKIE)
    if cookie_sid is not None and cookie_sid != sid:
        raise HTTPException(status_code=403, detail="cookie sid does not match URL sid")


def _verify_sid_cookie_strict(request: Request, sid: str) -> None:
    """POST-side cookie check: rejects missing OR mismatched cookies.

    Plan §24.4 row "any POST w/ wrong cookie sid → 403" — a cookieless
    POST would otherwise let an attacker drive the entire flow with only
    the URL sid.
    """
    cookie_sid = request.cookies.get(SESSION_COOKIE)
    if cookie_sid is None or cookie_sid != sid:
        raise HTTPException(status_code=403, detail="cookie sid does not match URL sid")


async def _load_or_404(store: SessionStore, sid: str) -> FormState:
    state = await store.get(sid)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return state


def _form_to_payload(step: str, form: FormData) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    fields = STEP_MODELS[step].model_fields
    for field_name in fields:
        if field_name in LIST_FIELDS:
            values = [v for v in form.getlist(field_name) if v]
            payload[field_name] = values or None
            continue
        raw = form.get(field_name)
        payload[field_name] = raw if raw not in (None, "") else None
    return payload


def _parse_step_form(step: str, payload: dict[str, Any]) -> tuple[Any | None, dict[str, str]]:
    model_cls = STEP_MODELS[step]
    try:
        parsed = model_cls.model_validate(payload)
    except ValidationError as exc:
        return None, _validation_errors_to_keys(step, exc, payload)

    required_errors = _required_field_errors(step, payload)
    if required_errors:
        return None, required_errors
    errors = _post_parse_validation(step, parsed, payload)
    if errors:
        return None, errors
    return parsed, {}


def _required_field_errors(step: str, payload: dict[str, Any]) -> dict[str, str]:
    """Emit `<field>_required` for any required slot whose payload is empty.

    Step pydantic models declare every field as Optional so empty form bodies
    parse cleanly; the required-field invariant is enforced here against the
    closed `STEP_REQUIRED_FIELDS` table per plan §13.
    """
    required = STEP_REQUIRED_FIELDS.get(step, frozenset())
    return {
        field: f"{field}_required" for field in required if payload.get(field) in (None, "", [])
    }


def _post_parse_validation(step: str, _parsed: Any, payload: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if step == "address":
        postcode = payload.get("address_postcode")
        if isinstance(postcode, str) and postcode:
            postcode_result = validate_postcode(postcode)
            if postcode_result.is_err():
                errors["address_postcode"] = postcode_result.unwrap_err()
    if step == "driver-1":
        dob = payload.get("driver_1_dob")
        if isinstance(dob, str) and dob:
            dob_result = validate_dob(dob)
            if dob_result.is_err():
                errors["driver_1_dob"] = dob_result.unwrap_err()
    return errors


def _validation_errors_to_keys(
    _step: str, exc: ValidationError, payload: dict[str, Any]
) -> dict[str, str]:
    errors: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        if not loc:
            continue
        field = str(loc[0])
        kind = err.get("type", "validation_error")
        provided_missing = payload.get(field) in (None, "", [])
        if provided_missing:
            errors[field] = f"{field}_required"
        else:
            suffix = _PYDANTIC_KIND_TO_KEY_SUFFIX.get(kind, "format_wrong")
            errors[field] = f"{field}_{suffix}"
    return errors


def _render_step(
    request: Request,
    sid: str,
    step: str,
    state: FormState,
    errors: dict[str, str],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    templates = request.app.state.templates
    persona_data = getattr(state, STEP_TO_ATTR[step], None)
    context = {
        "sid": sid,
        "csrf_token": "",
        "step_name": step,
        "errors": errors,
        "field_values": persona_data.model_dump() if persona_data is not None else {},
    }
    response: HTMLResponse = templates.TemplateResponse(
        request,
        STEP_TO_TEMPLATE[step],
        context,
        status_code=status_code,
    )
    return response


def _logical_pointer(state: FormState) -> int:
    for index, slug in enumerate(STEP_ORDER):
        attr = STEP_TO_ATTR[slug]
        if getattr(state, attr) is None:
            return index
    return len(STEP_ORDER) - 1


def _logical_pointer_label(state: FormState) -> str:
    return STEP_ORDER[_logical_pointer(state)]


def _next_step(current: str) -> str | None:
    index = STEP_ORDER.index(current)
    if index + 1 >= len(STEP_ORDER):
        return None
    return STEP_ORDER[index + 1]


def _all_steps_complete(state: FormState) -> bool:
    # The review step has no fields and is treated as the submit confirmation
    # in the POST flow; its sub-model is never required to be populated for
    # `_render_quote_result` to fire.
    required_slugs = [slug for slug in STEP_ORDER if slug != "review"]
    return all(getattr(state, STEP_TO_ATTR[slug]) is not None for slug in required_slugs)


def _render_quote_result(request: Request, sid: str, state: FormState) -> HTMLResponse:
    persona_spec = request.app.state.persona_spec
    quote_spec = PersonaQuoteSpec(
        premium_seed_offset=persona_spec.premium_seed_offset,
        addon_catalog=persona_spec.addon_catalog,
    )
    premium = compute_premium(state, quote_spec)
    templates = request.app.state.templates
    response: HTMLResponse = templates.TemplateResponse(
        request,
        "quote_result.html",
        {
            "sid": sid,
            "csrf_token": "",
            "premium_total": _format_currency(premium.total, request.app.state.settings.persona),
            "addons": [
                {"name": addon.name, "label": addon.name.replace("_", " "), "price": addon.price}
                for addon in premium.addons
            ],
        },
    )
    return response


def _format_currency(amount: Any, persona: Persona) -> str:
    if persona is Persona.B:
        return f"£{amount:.2f}"
    if persona is Persona.C:
        return f"{amount:,.2f} GBP"
    return f"£{amount:,.2f}"


def _emit_state_transition(
    *,
    session_id: str,
    from_state: str,
    to_state: str,
    step_name: str,
    field_names: frozenset[str],
) -> None:
    _logger.info(
        "state_transition",
        session_id=session_id,
        from_state=from_state,
        to_state=to_state,
        step_name=step_name,
        field_names=tuple(sorted(field_names)),
    )


def _persona_c_get_step(
    request: Request, sid: str, step: str, difficulty: Difficulty
) -> HTMLResponse:
    """Backwards-compatible persona_c GET handler from section 03 prototype.

    Section 10 replaces this with the full persona_c surface. Until then the
    prototype contract (htmx fragment on MEDIUM/HARD, full-page on EASY) must
    keep test_htmx_negotiation green.
    """
    if step != "vehicle":
        raise HTTPException(status_code=404, detail="route deferred to section 10")

    templates = request.app.state.templates
    headers = {HX_RESWAP_HEADER: HX_RESWAP_VALUE} if difficulty is not Difficulty.EASY else None
    response: HTMLResponse = templates.TemplateResponse(
        request,
        "step_01_vehicle.html",
        {"sid": sid, "csrf_token": ""},
        headers=headers,
    )
    return response


__all__ = ["router"]
