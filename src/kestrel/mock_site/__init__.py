"""Mock UK insurance quote site for kestrel adapter testing.

Public surface: app factory and the three core enums + Settings.
Everything else is split-internal. Adapters depend only on rendered
HTML over HTTP, never on Python types from this package.
"""

from __future__ import annotations

from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, FieldIdStrategy, Persona, Settings

__all__ = [
    "Difficulty",
    "FieldIdStrategy",
    "Persona",
    "Settings",
    "create_app",
]
