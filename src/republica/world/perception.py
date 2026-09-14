"""Medios y percepcion (ADR 005 secc. 4, `data/media_consumption.csv`).

Cada cohorte (`world/cohorts.py`) tiene variables percibidas propias
(`perceived_inflation_c`, `perceived_unemployment_c`, `sentiment_c`), que
solo `PUBLISH_STORY` puede sesgar (`features.media`). Los medios **nunca**
tocan una variable real del pais: `step_perception` solo lee
`inflation'`/`unemployment'` (ya calculadas por `world/economy.py`) y
devuelve percepciones nuevas -- nunca un `WorldState`.

Deliberadamente desacoplado de `engine`/`actors` (igual que el resto de
`world/`): `MediaAction` es una tupla liviana en vez de
`engine.actions.Action`, armada por el llamador (`engine/simulation.py`)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from republica.world.cohorts import Cohort, CohortState
from republica.world.config import DEFAULT_DATA_DIR
from republica.world.state import clamp

DEFAULT_MEDIA_CONSUMPTION_PATH = DEFAULT_DATA_DIR / "media_consumption.csv"

#: `q` de la transicion (ADR 005 secc. 4.4, literal): 0.4 para
#: inflacion/desempleo percibidos, 0.3 para sentimiento (ancla en 0).
Q_PERCEPTION = 0.4
Q_SENTIMENT = 0.3

#: Sesgo por frame, por punto de `influence.public` del medio (ADR 005 secc.
#: 4.3, tabla literal). `scandal` no sesga percepcion de
#: inflacion/desempleo (solo `sentiment_c`); su efecto sobre
#: `institutional_confidence` sigue el camino de ADR 003
#: (`engine/consequences.py`, sin tocar: ver Notas de implementacion).
FRAME_BIAS: dict[str, dict[str, float]] = {
    "crisis": {"inflation": 1.5, "unemployment": 2.0, "sentiment": -10.0},
    "recovery": {"inflation": -0.8, "unemployment": -1.0, "sentiment": 6.0},
    "scandal": {"inflation": 0.0, "unemployment": 0.0, "sentiment": -6.0},
    "neutral": {"inflation": 0.0, "unemployment": 0.0, "sentiment": 0.0},
}

#: Polaridad de cada frame (ADR 005 secc. 4.5, literal solo para "crisis <->
#: negativo"; `recovery` es el positivo simetrico y `scandal` mala noticia
#: -> negativo, documentado en Notas de implementacion). `neutral` no tiene
#: polaridad: no hay drift de audiencia ese mes para ese medio.
FRAME_POLARITY: dict[str, int] = {"crisis": -1, "recovery": 1, "scandal": -1}

AUDIENCE_DRIFT_RATE = 0.02
AUDIENCE_MIN = 0.05
AUDIENCE_MAX = 0.6

#: Rango declarado de `perceived_inflation_c`/`perceived_unemployment_c`/
#: `sentiment_c` (ADR 005 secc. 4.1, literal).
PERCEPTION_RANGE = (-100.0, 100.0)


@dataclass(frozen=True)
class MediaAction:
    """Una `PUBLISH_STORY` autorizada de este mes, ya resuelta a los datos
    que `step_perception`/`compute_bias` necesitan."""

    outlet_id: str
    frame: str
    target_bloc: str
    influence_public: float


@dataclass
class PerceptionRecord:
    """`kind: "perception"`, una linea por mes (ADR 005 secc. 4, deliverable
    5): perceived vs. real por cohorte mas `perception_gap`."""

    month: int
    real_inflation: float
    real_unemployment: float
    perception_gap: float
    cohorts: dict[str, dict[str, float]]
    outlet_influence: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "perception",
            "month": self.month,
            "real_inflation": round(self.real_inflation, 3),
            "real_unemployment": round(self.real_unemployment, 3),
            "perception_gap": round(self.perception_gap, 3),
            "cohorts": self.cohorts,
            "outlet_influence": {k: round(v, 3) for k, v in self.outlet_influence.items()},
        }


def load_media_consumption(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """`data/media_consumption.csv` -> `{cohort_id: {outlet_id: share}}`,
    shares que suman 1 por cohorte (ADR 005 secc. 4.2). Las columnas
    (`media_nacional`, `media_popular`, `media_mercado`) son literalmente
    los ids de las fichas `data/actors/media_*.yaml`, sin transformar."""
    p = Path(path) if path is not None else DEFAULT_MEDIA_CONSUMPTION_PATH
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        out: dict[str, dict[str, float]] = {}
        for row in reader:
            cohort_id = row["cohort"]
            out[cohort_id] = {key: float(value) for key, value in row.items() if key != "cohort"}
        return out


def compute_bias(
    cohorts: list[Cohort],
    media_actions: list[MediaAction],
    consumption: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """`bias_pi_c`/`bias_u_c`/`bias_sent_c` por cohorte (ADR 005 secc. 4.3/
    4.4): `PUBLISH_STORY.target_bloc` limita el efecto a esa cohorte; `all`
    (o cualquier valor que no sea un id de cohorte) lo reparte por
    `consumption` (secc. 4.2)."""
    bias = {c.id: {"inflation": 0.0, "unemployment": 0.0, "sentiment": 0.0} for c in cohorts}
    cohort_ids = set(bias)
    for action in media_actions:
        table = FRAME_BIAS.get(action.frame, FRAME_BIAS["neutral"])
        if not any(table.values()):
            continue
        if action.target_bloc in cohort_ids:
            target = bias[action.target_bloc]
            for key, value in table.items():
                target[key] += value * action.influence_public
        else:
            for cohort_id, shares in consumption.items():
                if cohort_id not in bias:
                    continue
                share = shares.get(action.outlet_id, 0.0)
                if not share:
                    continue
                target = bias[cohort_id]
                for key, value in table.items():
                    target[key] += share * value * action.influence_public
    return bias


def step_perception(
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    bias: dict[str, dict[str, float]],
    real_inflation: float,
    real_unemployment: float,
) -> dict[str, CohortState]:
    """Transicion de `perceived_inflation_c`/`perceived_unemployment_c`/
    `sentiment_c` (ADR 005 secc. 4.4). `approval_c` viaja sin tocar: la
    actualiza `world/cohorts.py::step_cohorts`, que corre despues (ADR 005
    secc. 5, pasos 8 y 9)."""
    lo, hi = PERCEPTION_RANGE
    out: dict[str, CohortState] = {}
    for c in cohorts:
        cs = cohort_state[c.id]
        b = bias.get(c.id) or {"inflation": 0.0, "unemployment": 0.0, "sentiment": 0.0}
        real_unemployment_c = real_unemployment + c.u_offset
        perceived_inflation = cs.perceived_inflation + Q_PERCEPTION * (
            real_inflation + b["inflation"] - cs.perceived_inflation
        )
        perceived_unemployment = cs.perceived_unemployment + Q_PERCEPTION * (
            real_unemployment_c + b["unemployment"] - cs.perceived_unemployment
        )
        sentiment = cs.sentiment + Q_SENTIMENT * (b["sentiment"] - cs.sentiment)
        out[c.id] = CohortState(
            approval=cs.approval,
            sentiment=clamp(sentiment, lo, hi),
            perceived_inflation=clamp(perceived_inflation, lo, hi),
            perceived_unemployment=clamp(perceived_unemployment, lo, hi),
        )
    return out


def sync_to_real(
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    real_inflation: float,
    real_unemployment: float,
) -> dict[str, CohortState]:
    """`perceived_* = real` cada mes, sin el retraso de `step_perception`
    (ADR 005 secc. 4, `features.media = False`): sin medios no hay sesgo NI
    motivo para que la percepcion quede rezagada de la realidad -- sesgo 0
    en `step_perception` deja `sentiment_c` en 0 igual (ancla 0, sin sesgo
    que lo mueva), pero el filtro `q` de inflacion/desempleo seguiria un
    paso atras de una inflacion real que jamas es perfectamente constante,
    lo que le impediria a `world/cohorts.py::step_cohorts` reproducir v0.1
    exactamente con cohortes homogeneas (test de aceptacion 3, ADR 005 secc.
    7): ver Notas de implementacion."""
    out: dict[str, CohortState] = {}
    for c in cohorts:
        cs = cohort_state[c.id]
        out[c.id] = CohortState(
            approval=cs.approval,
            sentiment=0.0,
            perceived_inflation=real_inflation,
            perceived_unemployment=real_unemployment + c.u_offset,
        )
    return out


def perception_gap(
    cohorts: list[Cohort], cohort_state: dict[str, CohortState], real_inflation: float
) -> float:
    """`Σ pop_share_c · (perceived_inflation_c − inflation')` (ADR 005 secc.
    4.4): metrica registrada, no realimenta el motor."""
    return sum(
        c.pop_share * (cohort_state[c.id].perceived_inflation - real_inflation) for c in cohorts
    )


def audience_alignment(
    frame: str, cohorts: list[Cohort], cohort_state: dict[str, CohortState]
) -> float | None:
    """Fraccion de cohortes cuyo `sentiment_c` tiene el mismo signo que la
    polaridad de `frame` (ADR 005 secc. 4.5). `None` para `neutral` (sin
    polaridad declarada: ese medio no gana ni pierde audiencia este mes)."""
    polarity = FRAME_POLARITY.get(frame)
    if polarity is None or not cohorts:
        return None
    aligned = sum(
        1
        for c in cohorts
        if (polarity > 0) == (cohort_state[c.id].sentiment > 0)
        and cohort_state[c.id].sentiment != 0.0
    )
    return aligned / len(cohorts)


def drift_audience(
    frame: str,
    influence_public: float,
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
) -> float:
    """`influence.public_m'` (ADR 005 secc. 4.5, literal), acotado a
    `[0.05, 0.6]`: un medio que insiste en un frame cuando la gente no
    coincide (`alineacion < 0.5`) pierde audiencia."""
    alignment = audience_alignment(frame, cohorts, cohort_state)
    if alignment is None:
        return clamp(influence_public, AUDIENCE_MIN, AUDIENCE_MAX)
    updated = influence_public + AUDIENCE_DRIFT_RATE * (alignment - 0.5)
    return clamp(updated, AUDIENCE_MIN, AUDIENCE_MAX)
