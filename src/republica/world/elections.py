"""Elecciones (ADR 006 secc. 2): intencion de voto por cohorte y partido
(secc. 2.1/2.2), sistema electoral a dos vueltas + D'Hondt (secc. 2.3),
transicion de gobierno (secc. 2.4) y las funciones que usan las acciones de
campana `CAMPAIGN`/`PROMISE` (secc. 2.5).

Gateado por `features.elections` (default `True`, solo con `features.actors`
tambien activo): con `features.elections = False`, `engine/simulation.py` no
llama nada de este modulo, `country.months` sigue terminando en `survived`
como antes de ADR 006 (ver Notas de implementacion)."""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from republica.actors.sheet import ActorSheet
from republica.world.config import DEFAULT_DATA_DIR, Province
from republica.world.provinces import ProvinceRecord

if TYPE_CHECKING:
    from republica.ai.memory import MemoryStore
    from republica.engine.consequences import Relationships
    from republica.world.cohorts import Cohort, CohortState
    from republica.world.config import Party

DEFAULT_LOYALTY_PATH = DEFAULT_DATA_DIR / "cohorts_loyalty.csv"
#: `data/cohort_provinces.csv` (calibracion, secc. 2.2 `regional_bonus_c,p`):
#: peso de poblacion de cada cohorte por provincia (`Σ_p peso_c,p == 1`).
#: Opcional -- ver `load_province_weights`.
DEFAULT_PROVINCE_WEIGHTS_PATH = DEFAULT_DATA_DIR / "cohort_provinces.csv"
#: `data/actors/ministers/<party_id>.yaml` (ADR 006 secc. 2.4).
MINISTERS_DIR = DEFAULT_DATA_DIR / "actors" / "ministers"

#: Pesos por defecto (ADR 006 secc. 2.2, literal).
WEIGHTS: dict[str, float] = {
    "v_econ": 0.35,
    "v_ideo": 0.25,
    "v_appr": 0.15,
    "v_loy": 0.15,
    "v_reg": 0.05,
    "v_camp": 0.03,
    "v_evt": 0.02,
}

#: `tau` del softmax de intencion de voto por cohorte (secc. 2.2: "τ = 0.35"
#: literal, RECALIBRADO -- ver docs/CALIBRATION_LOG.md). Con los pesos
#: literales de la formula, el rango tipico de `util_c,p` entre partidos de
#: una misma cohorte es de apenas 0.1-0.3 (`v_ideo=0.25`/`v_loy=0.15` son los
#: terminos dominantes en la linea de base sin campana/economia/eventos); un
#: `τ` de 0.35 aplasta esas diferencias a casi nada (`exp(0.2/0.35)≈1.76`
#: contra las 5 opciones -> reparto casi uniforme, el bug que reporta el
#: encargo de calibracion). `τ = 0.15` mantiene el resultado dentro de rango
#: de softmax razonable (`exp(0.2/0.15)≈3.79`) sin volverlo una eleccion
#: cuasi-determinista.
TAU_SHARE = 0.15
#: `tau` del softmax de transferencia de votos en el balotaje (secc. 2.3,
#: literal).
TAU_RUNOFF = 0.5
#: Ruido por partido antes de renormalizar (secc. 2.2, literal: `N(0, 1.5)`).
VOTE_NOISE_STD = 1.5
#: Turnout constante si `cohorts_loyalty.csv` no trae la columna (secc. 2.2,
#: "constante 0.75 -- tu decision", documentado en Notas de implementacion:
#: se eligio traer `turnout` como columna del mismo CSV en vez de una
#: constante global, con 0.75 solo como fallback).
DEFAULT_TURNOUT = 0.75

#: Umbrales de la primera vuelta (ADR 006 secc. 2.3, literal).
FIRST_ROUND_ABSOLUTE_PCT = 45.0
FIRST_ROUND_PLURALITY_PCT = 40.0
FIRST_ROUND_MARGIN_PP = 10.0
#: Bancas y umbral del Congreso (secc. 2.3, literal).
CONGRESS_SEATS = 100
SEAT_THRESHOLD_PCT = 3.0

#: Luna de miel / continuidad (ADR 006 secc. 2.4, literal).
HONEYMOON_BONUS = 8.0
INCUMBENT_WIN_BONUS = 5.0

#: Ventana de campana (secc. 2.1/2.5, literal: meses 45-48 de un mandato de
#: 48) expresada como "ultimos N meses del mandato", para que funcione con
#: cualquier `term_length` (no solo 48).
CAMPAIGN_WINDOW_MONTHS = 4

#: Meses posteriores a una eleccion en los que una `PROMISE` puede
#: incumplirse (secc. 2.5, literal: "6 meses").
PROMISE_WINDOW_MONTHS = 6


def is_campaign_month(month: int, term_length: int) -> bool:
    """`True` si `month` cae en los ultimos `CAMPAIGN_WINDOW_MONTHS` meses
    del mandato en curso (secc. 2.1/2.5: meses 45-48 de un mandato de 48)."""
    if term_length <= 0:
        return False
    month_in_term = ((month - 1) % term_length) + 1
    return month_in_term > term_length - CAMPAIGN_WINDOW_MONTHS


def is_election_month(month: int, term_length: int) -> bool:
    return term_length > 0 and month % term_length == 0


@dataclass
class LoyaltyTable:
    loyalty: dict[tuple[str, str], float] = field(default_factory=dict)
    turnout: dict[str, float] = field(default_factory=dict)

    def get_loyalty(self, cohort_id: str, party_id: str) -> float:
        return self.loyalty.get((cohort_id, party_id), 0.0)

    def get_turnout(self, cohort_id: str) -> float:
        return self.turnout.get(cohort_id, DEFAULT_TURNOUT)


def load_loyalty(path: str | Path | None = None) -> LoyaltyTable:
    """Carga `data/cohorts_loyalty.csv` (ADR 006 secc. 2.2: "matriz de
    lealtad inicial", ver docstring del CSV para los valores y como se
    inventaron)."""
    p = Path(path) if path is not None else DEFAULT_LOYALTY_PATH
    table = LoyaltyTable()
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cohort_id = row["cohort_id"]
            party_id = row["party_id"]
            table.loyalty[(cohort_id, party_id)] = float(row["loyalty"])
            if cohort_id not in table.turnout:
                table.turnout[cohort_id] = float(row["turnout"])
    return table


def load_province_weights(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """Carga `data/cohort_provinces.csv` (calibracion: `cohort_id,
    province_id, weight`, `Σ_p weight_c,p == 1` por cohorte) -- mapea cada
    cohorte a la mezcla de provincias donde vive, para `regional_bonus_c,p`
    (secc. 2.2). Opcional (encargo de calibracion, secc. 2.1/2.2 nota impl.
    #10 original): si el archivo no existe devuelve `{}` (mismo
    comportamiento que antes -- `regional_bonus_c,p = 0` para todos)."""
    p = Path(path) if path is not None else DEFAULT_PROVINCE_WEIGHTS_PATH
    if not p.exists():
        return {}
    out: dict[str, dict[str, float]] = {}
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bucket = out.setdefault(row["cohort_id"], {})
            bucket[row["province_id"]] = float(row["weight"])
    return out


#: Escalas de `province_performance` (calibracion, sin ADR: la seccion 2.1/
#: 2.2 solo dice "gobernadores del partido con approval alta en la region",
#: sin formula -- ver docs/ADR_006_memory_elections.md, nota de calibracion
#: agregada). `income_p` es un indice centrado en 100 (`world/provinces.py`);
#: una desviacion de 20 puntos (shock/transferencia grande) satura el
#: termino a +-1. `unemployment_p` se compara contra el desempleo nacional
#: del mismo mes; una brecha de 5pp (mas que el `u_offset` mas extremo de
#: `provinces.csv`, +-4) satura el termino a +-1.
REGIONAL_INCOME_SCALE = 20.0
REGIONAL_UNEMPLOYMENT_SCALE = 5.0


def province_performance(
    province_records: list[ProvinceRecord], national_unemployment: float
) -> dict[str, float]:
    """`perf_p` (calibracion): que tan bien le va a la provincia `p` respecto
    del pais, usado como proxy de la popularidad de su gobernador (secc. 2.1/
    2.2: "gobernadores del partido con approval alta en la region", el ADR no
    da formula -- `income_p`/`unemployment_p` de `world/provinces.py` son las
    unicas variables provinciales que existen). Acotado a `[-1, 1]`, mismo
    orden que los demas terminos del util antes de los pesos."""
    perf: dict[str, float] = {}
    for pr in province_records:
        income_term = (pr.income_p - 100.0) / REGIONAL_INCOME_SCALE
        unemployment_gap = pr.unemployment_p - national_unemployment
        unemployment_term = -unemployment_gap / REGIONAL_UNEMPLOYMENT_SCALE
        perf[pr.id] = max(-1.0, min(1.0, income_term + unemployment_term))
    return perf


def compute_regional_bonus(
    cohorts: list[Cohort],
    provinces: list[Province],
    province_records: list[ProvinceRecord],
    province_weights: dict[str, dict[str, float]],
    national_unemployment: float,
) -> dict[tuple[str, str], float]:
    """`regional_bonus_c,p` (secc. 2.2): `Σ_prov peso_c,prov · perf_prov` para
    el partido que gobierna esa provincia (`data/provinces.csv ->
    governor_party`), 0 para los demas partidos ahi. Cero si no hay datos de
    provincia para una cohorte (mismo default que antes de esta calibracion:
    ver ADR 006 nota de implementacion #10, ahora resuelta)."""
    governor_by_province = {p.id: p.governor_party for p in provinces}
    perf = province_performance(province_records, national_unemployment)
    bonus: dict[tuple[str, str], float] = {}
    for c in cohorts:
        for prov_id, weight in province_weights.get(c.id, {}).items():
            party_id = governor_by_province.get(prov_id)
            if party_id is None:
                continue
            key = (c.id, party_id)
            bonus[key] = bonus.get(key, 0.0) + weight * perf.get(prov_id, 0.0)
    return bonus


def pos(x: float) -> float:
    return x if x > 0.0 else 0.0


def econ_vote(
    cohort: Cohort,
    delta_real_wage_pct_12m: float,
    delta_unemployment_12m: float,
    perceived_inflation: float,
) -> float:
    """`econ_vote_c` (ADR 006 secc. 2.2, literal), con las sensibilidades
    propias de la cohorte (`s_w`, `s_u`, `s_pi` de `cohorts.csv`, ADR 005
    secc. 3) en vez de un `s_w_c`/`s_u_c`/`s_pi_c` nuevo sin declarar."""
    return math.tanh(
        (
            delta_real_wage_pct_12m * cohort.s_w
            - delta_unemployment_12m * cohort.s_u
            - pos(perceived_inflation - 2.0) * cohort.s_pi
        )
        / 10.0
    )


def recent_events_term(
    memory_store: MemoryStore | None, cohort_id: str, now_turn: int, window: int = 6
) -> float:
    """`recent_events_c` (ADR 006 secc. 2.2: "shocks/escandalos ultimos 6
    meses (memoria de cohorte)"): fraccion negativa de eventos de memoria de
    la cohorte en la ventana, acotada a `[-1, 0]` (documentado en Notas de
    implementacion: el ADR no da formula exacta, solo la fuente)."""
    if memory_store is None:
        return 0.0
    events = memory_store.for_owner(cohort_id)
    count = sum(1 for e in events if e.sentiment < 0.0 and (now_turn - e.turn) <= window)
    return -min(1.0, count / 3.0)


def compute_vote_intention(
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    parties: list[Party],
    government_approval: float,
    loyalty: LoyaltyTable,
    *,
    delta_real_wage_pct_12m: float,
    delta_unemployment_12m: float,
    campaign_state: dict[str, dict[str, float]] | None = None,
    memory_store: MemoryStore | None = None,
    now_turn: int = 0,
    loyalty_adjustments: dict[tuple[str, str], float] | None = None,
    regional_bonus: dict[tuple[str, str], float] | None = None,
) -> dict[str, dict[str, float]]:
    """Intencion de voto por cohorte y partido (ADR 006 secc. 2.2):
    `{cohort_id: {party_id: share}}`, `share` ya normalizado por softmax
    dentro de cada cohorte (`Σ_p share_c,p == 1`).

    `regional_bonus` (secc. 2.2, `regional_bonus_c,p`) ya viene calculado
    (`compute_regional_bonus`, calibracion: ver docs/ADR_006_memory_elections.md
    nota de implementacion #10, ahora resuelta con `data/cohort_provinces.csv`)
    -- default `{}` (0 para todos) si el llamador no lo pasa, mismo
    comportamiento que antes de la calibracion."""
    campaign_state = campaign_state or {}
    loyalty_adjustments = loyalty_adjustments or {}
    regional_bonus = regional_bonus or {}
    out: dict[str, dict[str, float]] = {}
    for c in cohorts:
        cs = cohort_state[c.id]
        econ = econ_vote(c, delta_real_wage_pct_12m, delta_unemployment_12m, cs.perceived_inflation)
        evt = recent_events_term(memory_store, c.id, now_turn)
        util: dict[str, float] = {}
        for p in parties:
            u = 0.0
            if p.in_government:
                u += WEIGHTS["v_econ"] * econ
                u += WEIGHTS["v_appr"] * (government_approval - 50.0) / 50.0
            u += WEIGHTS["v_ideo"] * (1.0 - abs(c.econ_pref - p.economic))
            loy = loyalty.get_loyalty(c.id, p.id) + loyalty_adjustments.get((c.id, p.id), 0.0)
            u += WEIGHTS["v_loy"] * loy
            u += WEIGHTS["v_reg"] * regional_bonus.get((c.id, p.id), 0.0)
            camp = campaign_state.get(p.id, {})
            u += WEIGHTS["v_camp"] * (camp.get(c.id, 0.0) + camp.get("all", 0.0))
            u += WEIGHTS["v_evt"] * evt
            util[p.id] = u
        m = max(util.values())
        exps = {pid: math.exp((v - m) / TAU_SHARE) for pid, v in util.items()}
        total = sum(exps.values()) or 1.0
        out[c.id] = {pid: e / total for pid, e in exps.items()}
    return out


def aggregate_vote(
    cohorts: list[Cohort],
    share: dict[str, dict[str, float]],
    loyalty: LoyaltyTable,
    rng: random.Random,
) -> dict[str, float]:
    """`vote_p` (ADR 006 secc. 2.2, literal), en porcentaje de los votos
    validos (turnout ya aplicado), con ruido gaussiano por partido y
    renormalizado a que sume 100."""
    raw: dict[str, float] = {}
    for c in cohorts:
        t = loyalty.get_turnout(c.id)
        for pid, s in share[c.id].items():
            raw[pid] = raw.get(pid, 0.0) + c.pop_share * t * s
    total_raw = sum(raw.values()) or 1.0
    pct = {pid: v / total_raw * 100.0 for pid, v in raw.items()}
    noisy = {pid: max(0.0, v + rng.gauss(0.0, VOTE_NOISE_STD)) for pid, v in pct.items()}
    total_noisy = sum(noisy.values()) or 1.0
    return {pid: v / total_noisy * 100.0 for pid, v in noisy.items()}


def resolve_presidential(
    vote_pct: dict[str, float], parties: list[Party]
) -> tuple[str, dict[str, float] | None]:
    """Sistema a dos vueltas (ADR 006 secc. 2.3, literal). Devuelve
    `(winner_party_id, runoff_pct | None)`."""
    ranked = sorted(vote_pct.items(), key=lambda kv: kv[1], reverse=True)
    first_id, first_pct = ranked[0]
    second_id, second_pct = ranked[1]
    if first_pct > FIRST_ROUND_ABSOLUTE_PCT or (
        first_pct > FIRST_ROUND_PLURALITY_PCT and first_pct - second_pct >= FIRST_ROUND_MARGIN_PP
    ):
        return first_id, None

    parties_by_id = {p.id: p for p in parties}
    p1, p2 = parties_by_id[first_id], parties_by_id[second_id]
    base1, base2 = vote_pct[first_id], vote_pct[second_id]
    for pid, v in vote_pct.items():
        if pid in (first_id, second_id):
            continue
        other = parties_by_id.get(pid)
        if other is None:
            continue
        d1 = abs(other.economic - p1.economic)
        d2 = abs(other.economic - p2.economic)
        e1 = math.exp(-d1 / TAU_RUNOFF)
        e2 = math.exp(-d2 / TAU_RUNOFF)
        s = e1 + e2
        base1 += v * e1 / s
        base2 += v * e2 / s
    total = base1 + base2 or 1.0
    runoff = {first_id: base1 / total * 100.0, second_id: base2 / total * 100.0}
    winner = first_id if runoff[first_id] >= runoff[second_id] else second_id
    return winner, runoff


def dhondt(
    vote_pct: dict[str, float],
    seats_total: int = CONGRESS_SEATS,
    threshold_pct: float = SEAT_THRESHOLD_PCT,
) -> dict[str, int]:
    """Congreso proporcional D'Hondt sobre `vote_p`, umbral 3 % (ADR 006
    secc. 2.3, literal)."""
    eligible = {pid: v for pid, v in vote_pct.items() if v >= threshold_pct}
    if not eligible:
        eligible = dict(vote_pct)
    quotients: list[tuple[float, str]] = [
        (v / d, pid) for pid, v in eligible.items() for d in range(1, seats_total + 1)
    ]
    quotients.sort(key=lambda t: t[0], reverse=True)
    seats: dict[str, int] = dict.fromkeys(eligible, 0)
    for _, pid in quotients[:seats_total]:
        seats[pid] += 1
    for pid in vote_pct:
        seats.setdefault(pid, 0)
    return seats


@dataclass
class ElectionResult:
    """Resultado completo de una eleccion (para `ElectionRecord`, JSONL
    `kind: "election"`, ADR 006 secc. 2.4, literal)."""

    month: int
    intention: dict[str, dict[str, float]]
    first_round: dict[str, float]
    runoff: dict[str, float] | None
    winner: str
    seats: dict[str, int]
    incumbent_party: str

    @property
    def outcome_type(self) -> str:
        return "reelected" if self.winner == self.incumbent_party else "defeated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "election",
            "month": self.month,
            "intention": self.intention,
            "first_round": {k: round(v, 2) for k, v in self.first_round.items()},
            "runoff": ({k: round(v, 2) for k, v in self.runoff.items()} if self.runoff else None),
            "winner": self.winner,
            "seats": self.seats,
            "incumbent_party": self.incumbent_party,
            "outcome_type": self.outcome_type,
        }


def run_election(
    month: int,
    cohorts: list[Cohort],
    cohort_state: dict[str, CohortState],
    parties: list[Party],
    government_approval: float,
    loyalty: LoyaltyTable,
    rng: random.Random,
    *,
    delta_real_wage_pct_12m: float = 0.0,
    delta_unemployment_12m: float = 0.0,
    campaign_state: dict[str, dict[str, float]] | None = None,
    memory_store: MemoryStore | None = None,
    loyalty_adjustments: dict[tuple[str, str], float] | None = None,
    provinces: list[Province] | None = None,
    province_records: list[ProvinceRecord] | None = None,
    province_weights: dict[str, dict[str, float]] | None = None,
    national_unemployment: float | None = None,
) -> ElectionResult:
    """Orquesta secc. 2.2 + 2.3: intencion -> primera vuelta -> balotaje (si
    corresponde) -> bancas.

    `provinces`/`province_records`/`province_weights`/`national_unemployment`
    (calibracion, `regional_bonus_c,p`): los 4 son opcionales y solo tienen
    efecto juntos -- si falta alguno, `regional_bonus` queda en `{}` (0 para
    todos, mismo comportamiento que antes de esta calibracion)."""
    incumbent = next((p.id for p in parties if p.in_government), parties[0].id)
    regional_bonus = (
        compute_regional_bonus(
            cohorts, provinces, province_records, province_weights, national_unemployment
        )
        if provinces is not None
        and province_records is not None
        and province_weights is not None
        and national_unemployment is not None
        else None
    )
    intention = compute_vote_intention(
        cohorts,
        cohort_state,
        parties,
        government_approval,
        loyalty,
        delta_real_wage_pct_12m=delta_real_wage_pct_12m,
        delta_unemployment_12m=delta_unemployment_12m,
        campaign_state=campaign_state,
        memory_store=memory_store,
        now_turn=month,
        loyalty_adjustments=loyalty_adjustments,
        regional_bonus=regional_bonus,
    )
    first_round = aggregate_vote(cohorts, intention, loyalty, rng)
    winner, runoff = resolve_presidential(first_round, parties)
    seats = dhondt(first_round)
    return ElectionResult(
        month=month,
        intention=intention,
        first_round=first_round,
        runoff=runoff,
        winner=winner,
        seats=seats,
        incumbent_party=incumbent,
    )


# ---------------------------------------------------------------------------
# Transicion de gobierno (ADR 006 secc. 2.4)
# ---------------------------------------------------------------------------


def _load_minister_sheet(party_id: str) -> ActorSheet | None:
    path = MINISTERS_DIR / f"{party_id}.yaml"
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ActorSheet.model_validate(raw)


def build_post_election_parties(result: ElectionResult, parties: list[Party]) -> list[Party]:
    """`seats`/`in_government` de la proxima temporada (ADR 006 secc. 2.4:
    "las bancas de la eleccion reemplazan las de `parties.json` para el
    proximo mandato"). Las alianzas (`is_ally`) se resetean: no hay forma de
    saber, a partir del solo resultado electoral, que coalicion de gobierno
    arma el ganador -- se deja que `FORM_ALLIANCE` (ADR 003) las reconstruya
    durante el mandato (documentado en Notas de implementacion)."""
    return [
        p.model_copy(
            update={
                "seats": result.seats.get(p.id, p.seats),
                "in_government": p.id == result.winner,
                "is_ally": False,
                "coalition_weight": 1.0,
            }
        )
        for p in parties
    ]


def build_post_election_actors(
    result: ElectionResult, actors: dict[str, ActorSheet]
) -> dict[str, ActorSheet]:
    """Reemplaza `president`/`minister_economy` si `winner != incumbent`
    (ADR 006 secc. 2.4, literal): `president` se clona de `party_<winner>`
    (mismo `id`="president"/`role`="president", ideologia y relaciones del
    partido: "relaciones del nuevo presidente = las del partido"),
    `minister_economy` de `data/actors/ministers/<winner>.yaml` (si no hay
    ficha para ese partido -- solo existen las de los 4 no-FF -- el
    ministro actual sigue, documentado en Notas de implementacion). Los
    demas actores (incluidos los gobernadores y partidos) NO se tocan aca:
    "persisten con su memoria" (ADR literal)."""
    if result.winner == result.incumbent_party:
        return actors
    new_actors = dict(actors)
    party_sheet = actors.get(f"party_{result.winner}")
    if party_sheet is not None:
        new_actors["president"] = party_sheet.model_copy(
            update={"id": "president", "role": "president", "party": result.winner}
        )
    minister_sheet = _load_minister_sheet(result.winner)
    if minister_sheet is not None:
        new_actors["minister_economy"] = minister_sheet
    return new_actors


def reseed_president_relationships(relationships: Relationships, party_sheet: ActorSheet) -> None:
    """`relaciones del nuevo presidente = las del partido` (ADR 006 secc.
    2.4, literal): descarta toda relacion previa que involucre a
    `"president"` y la vuelve a sembrar desde `party_sheet.relationships`
    (mismo criterio de siembra que `Relationships.from_actors`, ADR 003
    secc. 11 punto 9)."""
    for key in [k for k in relationships.values if "president" in k]:
        del relationships.values[key]
    for other_id, value in party_sheet.relationships.items():
        if other_id == "president":
            continue
        relationships.values[frozenset(("president", other_id))] = float(value)


def honeymoon_approval(result: ElectionResult) -> float:
    """`approval` inicial post-eleccion (ADR 006 secc. 2.4, literal):
    `vote_p` del ganador + 8 (cambio de gobierno) o + 5 (oficialismo
    reelecto)."""
    bonus = INCUMBENT_WIN_BONUS if result.winner == result.incumbent_party else HONEYMOON_BONUS
    return result.first_round.get(result.winner, 50.0) + bonus
