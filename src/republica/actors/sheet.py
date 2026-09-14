"""Fichas de actores (ADR 003 secc. 2): `ActorSheet` + `load_actors(dir)`.

Las 29 fichas viven en `data/actors/*.yaml` (ya escritas a mano, no las toca
este modulo). Este modulo solo las tipa y les pone default (`relationships`
default 50 via `ActorSheet.relationship(other_id)`, `personality.pragmatism`
default 0.5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ACTORS_DIR = Path(__file__).resolve().parents[3] / "data" / "actors"

#: Los 9 roles de ADR 003 secc. 2.
Role = Literal[
    "president",
    "economy_minister",
    "central_bank",
    "governor",
    "party",
    "union",
    "business",
    "media",
    "social_bloc",
]

DEFAULT_RELATIONSHIP = 50


class Ideology(BaseModel):
    """Posicion ideologica en [-1, 1] (ADR 003 secc. 2)."""

    model_config = ConfigDict(extra="forbid")

    economic: float = Field(ge=-1.0, le=1.0)
    social: float = Field(ge=-1.0, le=1.0)
    federalism: float = Field(ge=-1.0, le=1.0)
    institutionalism: float = Field(ge=-1.0, le=1.0)

    def as_vector(self) -> tuple[float, float, float, float]:
        return (self.economic, self.social, self.federalism, self.institutionalism)


class Personality(BaseModel):
    """Rasgos en [0, 1] (ADR 003 secc. 2). `pragmatism` default 0.5."""

    model_config = ConfigDict(extra="forbid")

    ambition: float = Field(ge=0.0, le=1.0)
    risk_tolerance: float = Field(ge=0.0, le=1.0)
    loyalty: float = Field(ge=0.0, le=1.0)
    pragmatism: float = Field(default=0.5, ge=0.0, le=1.0)


class Influence(BaseModel):
    """Capacidad de incidencia en [0, 1] por canal (ADR 003 secc. 2)."""

    model_config = ConfigDict(extra="forbid")

    public: float = Field(ge=0.0, le=1.0)
    congress: float = Field(ge=0.0, le=1.0)
    streets: float = Field(ge=0.0, le=1.0)
    markets: float = Field(ge=0.0, le=1.0)


class ActorSheet(BaseModel):
    """Una ficha de actor (ADR 003 secc. 2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    role: Role
    party: str | None = None
    province: str | None = None
    sector: str | None = None
    ideology: Ideology
    personality: Personality
    interests: list[str] = Field(default_factory=list)
    influence: Influence
    relationships: dict[str, int] = Field(default_factory=dict)
    bio: str = ""

    def relationship(self, other_id: str) -> int:
        """Relacion con `other_id`, default 50 (ADR 003 secc. 2) si no figura
        explicitamente en la ficha."""
        return self.relationships.get(other_id, DEFAULT_RELATIONSHIP)


def _load_one(path: Path) -> ActorSheet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ActorSheet.model_validate(raw)


def load_actors(directory: str | Path | None = None) -> dict[str, ActorSheet]:
    """Carga todas las fichas `*.yaml` de `directory` (default `data/actors/`).

    Devuelve `{actor_id: ActorSheet}`. Levanta `ValueError` si dos fichas
    declaran el mismo `id`, o si el `id` de una ficha no coincide con el
    nombre de archivo esperado (chequeo de integridad barato).
    """
    d = Path(directory) if directory is not None else DEFAULT_ACTORS_DIR
    actors: dict[str, ActorSheet] = {}
    for path in sorted(d.glob("*.yaml")):
        sheet = _load_one(path)
        if sheet.id in actors:
            raise ValueError(f"id de actor duplicado: {sheet.id!r} ({path})")
        actors[sheet.id] = sheet
    return actors
