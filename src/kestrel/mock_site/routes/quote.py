"""Quote-flow routes. Phase B.5 prototype: persona_c vehicle GET only.

Section 06 (Phase E) expands to the full ten-step matrix across all
three personas. This module currently exposes a single handler that
serves to lock down the htmx fragment-vs-full-page negotiation contract
before the larger surface lands.
"""

from __future__ import annotations

import re
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from kestrel.mock_site.config import Difficulty, Persona

SID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{43}$")
HX_RESWAP_HEADER: Final[str] = "HX-Reswap"
HX_RESWAP_VALUE: Final[str] = "outerHTML"

router = APIRouter(prefix="/quote", tags=["quote"])


@router.get("/{sid}/vehicle", response_class=HTMLResponse)
async def get_vehicle(sid: str, request: Request) -> HTMLResponse:
    if not SID_PATTERN.fullmatch(sid):
        raise HTTPException(status_code=400, detail="invalid sid format")

    settings = request.app.state.settings
    if settings.persona is not Persona.C:
        # Phase B.5 prototype is persona_c-only. Section 06 expands to A and B.
        raise HTTPException(status_code=404, detail="route deferred to section 06")

    templates: Jinja2Templates = request.app.state.templates
    headers = (
        {HX_RESWAP_HEADER: HX_RESWAP_VALUE} if settings.difficulty is not Difficulty.EASY else None
    )
    return templates.TemplateResponse(
        request,
        "step_01_vehicle.html",
        {"sid": sid, "csrf_token": ""},
        headers=headers,
    )
