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
#: 4.3, tabla RECALIBRADA en la Quinta ronda de calibracion -- ver
#: docs/CALIBRATION_LOG.md). `scandal` no sesga percepcion de
#: inflacion/desempleo (solo `sentiment_c`); su efecto sobre
#: `institutional_confidence` sigue el camino de ADR 003
#: (`engine/consequences.py`, sin tocar: ver Notas de implementacion).
#:
#: Con la formula de estado estacionario de secc. 4.4 (`perceived_inflation_c
#: - inflation' -> bias_pi_c` cuando el sesgo es constante, porque el filtro
#: `q` converge a `perceived = real + bias`), la tabla ORIGINAL del ADR
#: (`crisis` `+1.5`/`+2.0`, `recovery` `-0.8`/`-1.0`) daba, a
#: `influence.public = AUDIENCE_MAX = 0.6` (el techo de secc. 4.5),
#: `1.5 · 0.6 = 0.9 pp/mes -> 10.8 pp` "anualizadas" (`× 12`, la misma cuenta
#: de docs/EMERGENCE_LOG.md) -- muy por encima del objetivo de calibracion
#: (<= ~4 pp anualizadas por medio y variable a influencia maxima).
#:
#: `inflation`/`unemployment` de `crisis`/`recovery` estan escalados
#: distinto (no un factor unico): `crisis` a ~0.2x (`0.30`/`0.40` ->
#: `2.16`/`2.88` pp anualizadas) y `recovery` a ~0.55-0.65x (`-0.52`/`-0.55`
#: -> `-3.74`/`-3.96` pp anualizadas), las dos por debajo de la cota de 4 pp
#: pero deliberadamente ASIMETRICAS: `crisis` es el frame que domina la
#: mayoria de los meses de la corrida de referencia (seed 7, taylor, 48
#: meses) para los tres medios, asi que escalarlo MUY chico alcanza para
#: bajar la brecha promedio (`perception_gap`) dentro de rango sin necesitar
#: tocar `recovery`; dejar `recovery` mas fuerte (cerca de su propia cota de
#: 4 pp) hace que un ciclo de crecimiento real (como el de los meses 11-18
#: de esa corrida) empuje la aprobacion lo suficiente como para que al menos
#: un medio se quede en `recovery`/`neutral` mas tiempo en vez de recaer en
#: `crisis` -- objetivo "al menos un medio con >= 30% de meses en frame no
#: crisis" de docs/CALIBRATION_LOG.md (Quinta ronda). Verificado empiricamente
#: (no derivado en cerrado): un escalado simetrico de `crisis`/`recovery` no
#: puede cumplir ambos objetivos a la vez (brecha promedio en [0.1, 0.6] pp
#: Y >= 30% de meses no-crisis) para ningun factor unico -- ver script de
#: calibracion en el scratchpad de la sesion, no versionado.
#:
#: `sentiment` no se toca: no entra en `perception_gap` (la metrica que fija
#: el objetivo) y solo se usa por signo en `audience_alignment`/
#: `drift_audience`, asi que escalarlo no cambia ese calculo.
FRAME_BIAS: dict[str, dict[str, float]] = {
    "crisis": {"inflation": 0.30, "unemployment": 0.40, "sentiment": -10.0},
    "recovery": {"inflation": -0.52, "unemployment": -0.55, "sentiment": 6.0},
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

#: Racha minima de meses consecutivos de frame contradictorio antes de
#: aplicar el castigo de reputacion (ADR 005 secc. 4.5, revisado v0.8).
CONTRADICTION_STREAK_MONTHS = 3
#: Costo de reputacion por mes mientras la contradiccion persiste (idem).
CONTRADICTION_PENALTY = 0.03
#: Ventana (meses) para medir "inflacion cayendo"/"desempleo subiendo" del
#: chequeo de contradiccion (ADR 005 secc. 4.5, revisado v0.8): comparar
#: contra el valor de hace `TREND_WINDOW_MONTHS` meses (no contra el mes
#: inmediato anterior) para no confundir una racha real con el ruido
#: exogeno mes a mes (ver `engine/simulation.py`, Notas de implementacion).
TREND_WINDOW_MONTHS = 4

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


def outlet_audience_weights(
    outlet_id: str, cohorts: list[Cohort], consumption: dict[str, dict[str, float]]
) -> dict[str, float]:
    """Pondera cada cohorte por su peso en la audiencia PROPIA de
    `outlet_id` (ADR 005 secc. 4.5, revisado v0.8): `pop_share_c ·
    consumption[c][outlet_id]` (secc. 4.2), normalizado a que sume 1. Antes
    de la Quinta ronda de calibracion, `audience_alignment` pesaba todas las
    cohortes por igual sin importar si consumian ese medio o no -- por eso
    los tres medios convergian a la misma audiencia y al mismo frame
    (docs/EMERGENCE_LOG.md, fila "convergencia de medios"): un medio de
    nicho (p.ej. `media_mercado`, fuerte en `middle_class`/`rural`) ganaba o
    perdia audiencia segun el humor de cohortes que ni siquiera lo leen.
    Si `outlet_id` no aparece en `consumption` para ninguna cohorte
    (audiencia total 0 -- csv incompleto o outlet nuevo sin fila), cae al
    peso poblacional parejo (mismo comportamiento que antes de este
    cambio)."""
    raw = {c.id: c.pop_share * consumption.get(c.id, {}).get(outlet_id, 0.0) for c in cohorts}
    total = sum(raw.values())
    if total <= 0.0:
        total_pop = sum(c.pop_share for c in cohorts) or 1.0
        return {c.id: c.pop_share / total_pop for c in cohorts}
    return {cid: w / total for cid, w in raw.items()}


def audience_alignment(
    frame: str,
    outlet_id: str,
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    consumption: dict[str, dict[str, float]],
) -> float | None:
    """Fraccion de la AUDIENCIA PROPIA de `outlet_id` (ponderada por
    `outlet_audience_weights`, no por poblacion total -- ADR 005 secc. 4.5,
    revisado v0.8) cuyo `sentiment_c` tiene el mismo signo que la polaridad
    de `frame`. `None` para `neutral` (sin polaridad declarada: ese medio no
    gana ni pierde audiencia este mes)."""
    polarity = FRAME_POLARITY.get(frame)
    if polarity is None or not cohorts:
        return None
    weights = outlet_audience_weights(outlet_id, cohorts, consumption)
    return sum(
        weights[c.id]
        for c in cohorts
        if (polarity > 0) == (cohort_state[c.id].sentiment > 0)
        and cohort_state[c.id].sentiment != 0.0
    )


def drift_audience(
    frame: str,
    outlet_id: str,
    influence_public: float,
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    consumption: dict[str, dict[str, float]],
) -> float:
    """`influence.public_m'` (ADR 005 secc. 4.5, revisado v0.8), acotado a
    `[0.05, 0.6]`: un medio que insiste en un frame cuando SU PROPIA
    audiencia no coincide (`alineacion < 0.5`, ponderada por
    `outlet_audience_weights`, no por poblacion total) pierde audiencia."""
    alignment = audience_alignment(frame, outlet_id, cohorts, cohort_state, consumption)
    if alignment is None:
        return clamp(influence_public, AUDIENCE_MIN, AUDIENCE_MAX)
    updated = influence_public + AUDIENCE_DRIFT_RATE * (alignment - 0.5)
    return clamp(updated, AUDIENCE_MIN, AUDIENCE_MAX)


def frame_contradicts_reality(
    frame: str, gdp_growth: float, inflation_delta: float, unemployment_delta: float
) -> bool:
    """Un frame "miente" contra la macro real de ese mes (ADR 005 secc. 4.5,
    revisado v0.8, deliverable nuevo de la Quinta ronda de calibracion):
    `crisis` mientras `gdp_growth > 2` e inflacion CAYENDO
    (`inflation_delta < 0`), o `recovery` mientras el desempleo SUBE
    (`unemployment_delta > 0`) y la inflacion ACELERA (`inflation_delta >
    0`). `scandal`/`neutral` nunca contradicen (no hacen una afirmacion
    macro que la realidad pueda desmentir)."""
    if frame == "crisis":
        return gdp_growth > 2.0 and inflation_delta < 0.0
    if frame == "recovery":
        return unemployment_delta > 0.0 and inflation_delta > 0.0
    return False


def update_contradiction_streak(
    streaks: dict[str, int],
    outlet_id: str,
    frame: str,
    gdp_growth: float,
    inflation_delta: float,
    unemployment_delta: float,
) -> int:
    """Actualiza `streaks` (in place, `Simulation.outlet_contradiction_streak`)
    con la racha de meses CONSECUTIVOS en que `outlet_id` publico un frame
    contradictorio (`frame_contradicts_reality`) y devuelve la racha
    resultante. Un mes sin contradiccion corta la racha a 0 (tiene que ser
    3+ meses SEGUIDOS, ADR 005 secc. 4.5 revisado v0.8 -- no 3 en total)."""
    if frame_contradicts_reality(frame, gdp_growth, inflation_delta, unemployment_delta):
        streaks[outlet_id] = streaks.get(outlet_id, 0) + 1
    else:
        streaks[outlet_id] = 0
    return streaks[outlet_id]


def reputation_penalty(streak: int) -> float:
    """`-0.03 · influence.public_m` por mes mientras la racha de
    contradiccion sea >= `CONTRADICTION_STREAK_MONTHS` (ADR 005 secc. 4.5,
    revisado v0.8), 0 en caso contrario."""
    return CONTRADICTION_PENALTY if streak >= CONTRADICTION_STREAK_MONTHS else 0.0
