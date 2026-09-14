"""Cohortes sociales (ADR 005 secc. 3, `data/cohorts.csv`).

Reemplaza en agregado la formula de aprobacion de gobierno de v0.1 (seccion
5.6 del spec) cuando `features.cohorts` esta activo: cada cohorte tiene su
propia `approval_c`, con sensibilidades propias y percepcion propia
(`perceived_inflation_c`, `world/perception.py`) en vez de la realidad.
`government_approval' = Σ pop_share_c · approval_c'`.

El estado de cada cohorte (`CohortState`) vive en `Simulation`/
`MonthRecord.cohorts`, no como 32 campos nuevos de `WorldState` (encargo):
`WorldState` sigue siendo las 20 variables de SPEC_v0.1.md secc. 2."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from republica.world.config import DEFAULT_DATA_DIR, Coefficients
from republica.world.state import Policy, WorldState, clamp, pos

DEFAULT_COHORTS_PATH = DEFAULT_DATA_DIR / "cohorts.csv"

#: Pesos literales de ADR 005 secc. 3 (no estan en `country.json →
#: coefficients`: son nuevos de este subsistema, no de las secciones 4/5 de
#: SPEC_v0.1 que `Coefficients` ya cubre).
TRANSFER_COEF = 2.0
TAX_COEF = 2.0
CRIME_COEF = 0.05
ECON_PREF_COEF = 3.0

#: Rango de `approval_c` (ADR 005 no lo declara explicito para la cohorte,
#: a diferencia de `perceived_*`/`sentiment_c` en secc. 4.1; se acota igual
#: que `government_approval` [0, 100] -- mismo rango del agregado que
#: `approval_c` promedia, documentado en Notas de implementacion).
APPROVAL_RANGE = (0.0, 100.0)


class Cohort(BaseModel):
    """Una fila de `cohorts.csv` (ADR 005 secc. 3)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    pop_share: float
    #: Ingreso relativo (metadato descriptivo/narrativo de `cohorts.csv`: no
    #: entra en la formula de transicion de ADR 005 secc. 3, que no lo usa).
    income: float
    u_offset: float
    s_pi: float
    s_u: float
    s_w: float
    s_tr: float
    s_tax: float
    s_crime: float
    trust: float
    econ_pref: float
    #: Actor de bloque social que representa a esta cohorte (ADR 005 secc.
    #: 3: `bloc_urban_workers -> urban_workers`, etc.); `None` para las
    #: cohortes sin actor propio (`young_professionals`, `retirees`,
    #: `students`: `cohorts.csv` deja la columna vacia).
    bloc_actor: str | None = None


@dataclass(frozen=True)
class CohortState:
    """Estado mutable de una cohorte mes a mes (ADR 005 secc. 3/4.1):
    `approval_c`, `sentiment_c`, `perceived_inflation_c`,
    `perceived_unemployment_c`."""

    approval: float
    sentiment: float
    perceived_inflation: float
    perceived_unemployment: float

    def to_dict(self) -> dict[str, float]:
        return {
            "approval_c": round(self.approval, 3),
            "sentiment_c": round(self.sentiment, 3),
            "perceived_inflation_c": round(self.perceived_inflation, 3),
            "perceived_unemployment_c": round(self.perceived_unemployment, 3),
        }


def load_cohorts(path: str | Path | None = None) -> list[Cohort]:
    """Carga `data/cohorts.csv` (8 cohortes, ADR 005 secc. 3)."""
    p = Path(path) if path is not None else DEFAULT_COHORTS_PATH
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [
            Cohort(
                id=row["id"],
                name=row["name"],
                pop_share=float(row["pop_share"]),
                income=float(row["income"]),
                u_offset=float(row["u_offset"]),
                s_pi=float(row["s_pi"]),
                s_u=float(row["s_u"]),
                s_w=float(row["s_w"]),
                s_tr=float(row["s_tr"]),
                s_tax=float(row["s_tax"]),
                s_crime=float(row["s_crime"]),
                trust=float(row["trust"]),
                econ_pref=float(row["econ_pref"]),
                bloc_actor=(row.get("bloc_actor") or None),
            )
            for row in reader
        ]


def init_cohort_state(cohorts: list[Cohort], state: WorldState) -> dict[str, CohortState]:
    """Estado inicial (ADR 005 secc. 3/4.1): `approval_c = 50` para todas,
    `sentiment_c = 0` (ancla, secc. 4.4), `perceived_* = real` en `t = 0`."""
    return {
        c.id: CohortState(
            approval=50.0,
            sentiment=0.0,
            perceived_inflation=state.inflation,
            perceived_unemployment=state.unemployment,
        )
        for c in cohorts
    }


def step_cohorts(
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    prev: WorldState,
    new: WorldState,
    policy: Policy,
    prev_policy: Policy,
    demand_gap: float,
    policy_direction: float,
    coeff: Coefficients,
    shock_approval: float = 0.0,
) -> tuple[dict[str, CohortState], float]:
    """Transicion de `approval_c` (ADR 005 secc. 3, reemplaza SPEC_v0.1
    secc. 5.6 en agregado). `prev`/`new` son el snapshot `t`/`t+1` (economia
    + sociedad ya corridas: usa `new.social_tension`/`new.crime_perception`
    ya actualizados por `world/society.py`). `cohort_state` ya trae
    `perceived_inflation_c` en `t+1` (`world/perception.py::step_perception`
    corre antes, ADR 005 secc. 5 pasos 8-9). `policy`/`prev_policy` son la
    `Policy` efectiva de este mes y la del mes pasado (para
    `Δprovincial_transfers`/`Δtax_rate`). `shock_approval` (ADR 005 no lo
    tabula: la formula de secc. 3 no lista un termino de shocks, a
    diferencia de SPEC_v0.1 secc. 5.6) es `shocks.term("shock_approval")`:
    sin el, eventos/dilemas/consecuencias de actores (`PUBLIC_STATEMENT`,
    `LOBBY_CONGRESS`, huelgas, etc.) dejarian de poder mover la aprobacion
    con `features.cohorts` activo -- se aplica por igual a cada cohorte
    (documentado en Notas de implementacion).

    Devuelve `(cohort_state con approval_c actualizado, government_approval
    agregada = Σ pop_share_c · approval_c')`."""
    delta_wage_pct = (new.real_wage - prev.real_wage) / prev.real_wage * 100.0
    delta_unemployment = new.unemployment - prev.unemployment
    delta_transfers = policy.provincial_transfers - prev_policy.provincial_transfers
    delta_tax = policy.tax_rate - prev_policy.tax_rate
    tension_term = pos(new.social_tension - coeff.tension_threshold) / 10.0
    crime_term = new.crime_perception - 50.0

    lo, hi = APPROVAL_RANGE
    out: dict[str, CohortState] = {}
    weighted_approval = 0.0
    for c in cohorts:
        cs = cohort_state[c.id]
        # Termino de inflacion: el ADR lo escribe como una unica resta lineal
        # (`- s_pi_c · e_pi · (perceived_inflation_c − 2)`), pero justo debajo
        # dice que con cohortes homogeneas "esto reproduce v0.1" -- y v0.1
        # (SPEC secc. 5.6) no es lineal, es partido en dos (`e_pi` castiga
        # solo la inflacion por ENCIMA de 2, `e_pi_low` premia, acotado, la
        # desinflacion por DEBAJO de 2). Con inflacion tipicamente bajo 2 en
        # tramos largos de una corrida (ConstantPolicy/TaylorPolicy sin
        # shocks), la version lineal del ADR diverge de v0.1 sin cota (un
        # premio lineal sin techo donde v0.1 lo acota) y el test de
        # aceptacion 3 (secc. 7, |diff| < 0.05/mes) no pasa. Se interpreta
        # el termino como "el mismo de v0.1, escalado por `s_pi_c` y con
        # `perceived_inflation_c` en vez de `inflation'`" -- documentado en
        # Notas de implementacion.
        inflation_term = coeff.e_pi_low * (
            coeff.pi_ref - clamp(cs.perceived_inflation, 0.0, coeff.pi_ref)
        ) - coeff.e_pi * pos(cs.perceived_inflation - coeff.pi_ref)
        approval = (
            cs.approval
            + c.s_w * coeff.e_w * delta_wage_pct
            - c.s_u * coeff.e_u * delta_unemployment
            + c.s_pi * inflation_term
            + coeff.e_g * demand_gap
            - coeff.e_t * tension_term
            + c.s_tr * TRANSFER_COEF * delta_transfers
            - c.s_tax * TAX_COEF * delta_tax
            - c.s_crime * CRIME_COEF * crime_term
            + coeff.e_rev * (coeff.approval_reversion - cs.approval)
            + ECON_PREF_COEF * c.econ_pref * policy_direction
            + shock_approval
        )
        approval = clamp(approval, lo, hi)
        out[c.id] = CohortState(
            approval=approval,
            sentiment=cs.sentiment,
            perceived_inflation=cs.perceived_inflation,
            perceived_unemployment=cs.perceived_unemployment,
        )
        weighted_approval += c.pop_share * approval
    return out, weighted_approval


def weighted_perceived_inflation(
    cohorts: list[Cohort], cohort_state: dict[str, CohortState]
) -> float:
    """`Σ pop_share_c · perceived_inflation_c` (ADR 005 secc. 3): reemplaza
    `inflation` en `consumer_confidence` (SPEC_v0.1 secc. 5.1) cuando
    `features.cohorts`."""
    return sum(c.pop_share * cohort_state[c.id].perceived_inflation for c in cohorts)


def cohort_by_bloc_actor(
    cohorts: list[Cohort], cohort_state: dict[str, CohortState]
) -> dict[str, CohortState]:
    """`{actor_id: CohortState}` para los bloques sociales que tienen
    cohorte propia (ADR 005 secc. 3: `bloc_urban_workers -> urban_workers`,
    etc. -- 5 de las 8 cohortes de `cohorts.csv`)."""
    return {c.bloc_actor: cohort_state[c.id] for c in cohorts if c.bloc_actor}
