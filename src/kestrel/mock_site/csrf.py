"""CSRF service.

Phase E (this section) ships the dependency surface as a no-op for
EASY and MEDIUM. Section 08 lands the HARD-mode HMAC token issue and
verify, plus the cookie attribute table per plan section 7.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request, Response

from kestrel.mock_site.config import Difficulty


@dataclass(frozen=True, slots=True)
class CsrfService:
    """Token issue + verify hooks. EASY/MEDIUM: empty token, no cookie."""

    secret: bytes

    def issue(self, _request: Request, _response: Response) -> str:
        return ""

    async def verify(self, _request: Request) -> None:
        return None


async def csrf_verify(request: Request) -> None:
    """FastAPI dependency. No-op outside HARD; section 08 fills HARD."""
    if request.app.state.settings.difficulty is not Difficulty.HARD:
        return
    service: CsrfService = request.app.state.csrf_service
    await service.verify(request)


__all__ = ["CsrfService", "csrf_verify"]
