"""Persona specs.

Plan section 25 catalogs the divergence axes between the three personas
shipped by the mock site. This module is the single source of truth for
the static persona attributes (template directory, premium offset, addon
catalog, field-id strategy per difficulty, addon catalog, persona-styled
copy). The runtime route handler reads from these specs via
``request.app.state.persona_spec``.

Persona B (this section) and persona C (next section) each get a full
entry; persona A keeps its established shape so the section 01-08 tests
do not regress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from kestrel.mock_site.config import Difficulty, FieldIdStrategy, Persona


@dataclass(frozen=True, slots=True)
class PersonaSpec:
    """Per-persona attributes consumed by the route handler and templates.

    ``template_dir`` resolves under ``src/kestrel/mock_site/templates``.
    ``field_id_strategy_by_difficulty`` maps each difficulty to the strategy
    the templates should apply when computing field ``id=`` attributes.
    ``premium_seed_offset`` and ``addon_catalog`` carry the section 15
    pricing inputs already established in section 06.
    """

    name: Persona
    template_dir: str
    premium_seed_offset: int
    addon_catalog: tuple[str, ...]
    field_id_strategy_by_difficulty: dict[Difficulty, FieldIdStrategy]
    css_filename: str

    def __repr__(self) -> str:
        return f"<PersonaSpec name={self.name}>"


_PERSONA_A: Final[PersonaSpec] = PersonaSpec(
    name=Persona.A,
    template_dir="persona_a",
    premium_seed_offset=0,
    addon_catalog=("breakdown", "legal_cover", "courtesy_car", "key_cover", "windscreen"),
    # Persona_a templates were shipped in section 02 with literal kebab-case
    # `id="vehicle-make"` attributes. The strategy is recorded here for
    # parity with persona_b but the persona_a Jinja templates ignore the
    # `field_ids` context and render their own literal ids.
    field_id_strategy_by_difficulty={
        Difficulty.EASY: FieldIdStrategy.STABLE,
        Difficulty.MEDIUM: FieldIdStrategy.STABLE,
        Difficulty.HARD: FieldIdStrategy.STABLE,
    },
    css_filename="persona_a.css",
)

_PERSONA_B: Final[PersonaSpec] = PersonaSpec(
    name=Persona.B,
    template_dir="persona_b",
    premium_seed_offset=175,
    addon_catalog=("breakdown", "legal_cover", "windscreen"),
    field_id_strategy_by_difficulty={
        Difficulty.EASY: FieldIdStrategy.STABLE,
        Difficulty.MEDIUM: FieldIdStrategy.MIXED,
        Difficulty.HARD: FieldIdStrategy.RANDOM_SUFFIX,
    },
    css_filename="persona_b.css",
)

_PERSONA_C: Final[PersonaSpec] = PersonaSpec(
    name=Persona.C,
    template_dir="persona_c",
    premium_seed_offset=350,
    addon_catalog=("breakdown", "courtesy_car", "key_cover"),
    field_id_strategy_by_difficulty={
        Difficulty.EASY: FieldIdStrategy.DATA_TEST_ONLY,
        Difficulty.MEDIUM: FieldIdStrategy.DATA_TEST_ONLY,
        Difficulty.HARD: FieldIdStrategy.DATA_TEST_ONLY,
    },
    css_filename="persona_c.css",
)


_PERSONA_SPECS: Final[dict[Persona, PersonaSpec]] = {
    Persona.A: _PERSONA_A,
    Persona.B: _PERSONA_B,
    Persona.C: _PERSONA_C,
}


def build_persona_spec(persona: Persona) -> PersonaSpec:
    return _PERSONA_SPECS[persona]


__all__ = ["PersonaSpec", "build_persona_spec"]
