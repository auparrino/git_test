"""Epocas historicas de un pais (ADR 013): `data/countries/<id>/eras/<era_id>/`
con `parties.json`, `actors/*.yaml`, `cohorts_loyalty.csv` y `governance.yaml`
propios, que reemplazan a los de Aurora cuando la fecha de inicio de una
corrida (`--start`) cae dentro de una epoca (ADR 013 secc. 1).

Este modulo es autonomo respecto de `engine/simulation.py` (que NO se toca,
salvo la unica linea documentada en el reporte de la tarea): la logica de
"cambio de epoca en la eleccion que cruza la frontera" y de "partido nuevo
que no existe hasta su fundacion" (ADR 013 secc. 5) vive enteramente en
`LoyaltyTable` (`world/elections.py`, extendida aca via `world/countries.py`)
mas el filtro por ventana activa que ya corre `compute_vote_intention` en
cada eleccion -- ver el docstring de `build_era_overlay` para el detalle del
mecanismo."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from republica.actors.sheet import ActorSheet, load_actors
from republica.world.cohorts import Cohort
from republica.world.config import DEFAULT_DATA_DIR
from republica.world.elections import DEFAULT_TURNOUT, TAU_SHARE, WEIGHTS, LoyaltyTable

ERAS_SUBDIR = "eras"

#: Epocas iniciales (ADR 013 secc. 1, literal): `id -> (start_year, end_year,
#: eleccion de apertura "YYYY-MM", ADR 013 secc. 4/6 punto 2: "1983, 2003,
#: 2015 primera vuelta"). El `id` es tambien el nombre del directorio.
KNOWN_ERAS: dict[str, tuple[int, int, str]] = {
    "1983-2001": (1983, 2001, "1983-12"),
    "2003-2015": (2003, 2015, "2003-05"),
    "2015-2023": (2015, 2023, "2015-12"),
}


@dataclass(frozen=True)
class Era:
    """Una epoca (ADR 013 secc. 1): cubre desde enero de `start_year` hasta
    diciembre de `end_year`, ambos inclusive."""

    id: str
    start_year: int
    end_year: int
    dir: Path
    anchor_election: str

    def covers(self, year: int, month: int) -> bool:
        return (self.start_year, 1) <= (year, month) <= (self.end_year, 12)


def eras_root(country_id: str) -> Path:
    return DEFAULT_DATA_DIR / "countries" / country_id / ERAS_SUBDIR


def list_eras(country_id: str) -> list[Era]:
    """Todas las epocas conocidas (`KNOWN_ERAS`) que efectivamente tienen
    directorio en `data/countries/<id>/eras/`, ordenadas por `start_year`."""
    root = eras_root(country_id)
    if not root.is_dir():
        return []
    out = []
    for name, (start_year, end_year, anchor) in KNOWN_ERAS.items():
        d = root / name
        if d.is_dir():
            out.append(Era(id=name, start_year=start_year, end_year=end_year, dir=d, anchor_election=anchor))
    out.sort(key=lambda e: e.start_year)
    return out


def _parse_ym(date: str) -> tuple[int, int]:
    y, m = date.split("-")
    return int(y), int(m)


def select_era(country_id: str, date: str) -> Era | None:
    """Epoca que cubre `date` (`YYYY-MM`, ADR 013 secc. 1/6 punto 1):
    `None` si ninguna la cubre (fallback a Aurora, con aviso -- lo emite el
    llamador, `world/countries.py::load_country_pack`)."""
    try:
        year, month = _parse_ym(date)
    except ValueError:
        return None
    for era in list_eras(country_id):
        if era.covers(year, month):
            return era
    return None


def load_era_parties(era: Era) -> list[dict]:
    return json.loads((era.dir / "parties.json").read_text(encoding="utf-8"))


def load_era_actors(era: Era) -> dict[str, ActorSheet]:
    return load_actors(era.dir / "actors")


def era_governance_path(era: Era) -> Path:
    return era.dir / "governance.yaml"


def party_exists(founded: int | str | None, date: str) -> bool:
    """`True` si un partido con fecha de fundacion `founded` (ano `int`, o
    `"YYYY-MM"`; `None` = preexistente, siempre existio) ya existe en
    `date` (`YYYY-MM`, ADR 013 secc. 5, literal: "un partido con `founded`
    posterior al inicio de la corrida no existe hasta su fundacion")."""
    if founded is None:
        return True
    year, month = _parse_ym(date)
    f_year, f_month = (int(founded), 1) if isinstance(founded, int) else _parse_ym(str(founded))
    return (year, month) >= (f_year, f_month)


def _month_index(start_year: int, start_month: int, year: int, month: int) -> int:
    """Indice de mes de una corrida que arranca en `start_year`/`start_month`
    (mismo calculo que `world/countries.py::historical_shocks_calendar`,
    1-based): puede dar <= 0 para fechas anteriores al arranque (un partido
    "preexistente" siempre tiene indice <= 1, o sea "siempre activo")."""
    return (year - start_year) * 12 + (month - start_month) + 1


def _advance_ym(year: int, month: int, months: int) -> tuple[int, int]:
    total = (month - 1) + months
    return year + total // 12, total % 12 + 1


def _first_election_at_or_after(month_index: int, term_length: int) -> int:
    """El primer mes de eleccion (`month % term_length == 0`, `world/
    elections.py::is_election_month`) que cae en `month_index` o despues:
    "cambia de epoca EN LA ELECCION que cruza la frontera" (ADR 013 secc.
    1, literal) es la eleccion programada, no necesariamente el mes exacto
    de enero en que la nueva epoca "empieza" en el calendario -- entre
    ambos no corre ninguna eleccion (el gobierno saliente sigue su
    mandato), asi que el conjunto de partidos activos en la PROXIMA
    eleccion es identico con cualquier corte intermedio; lo unico que tiene
    que coincidir exactamente es la clave de `LoyaltyTable.era_boundaries`
    contra el `month` real de esa eleccion, para que `ElectionResult.
    era_change` se ponga (ADR 013 secc. 6 punto 4)."""
    if term_length <= 0:
        return month_index
    return ((month_index + term_length - 1) // term_length) * term_length


# ---------------------------------------------------------------------------
# Superposicion multi-epoca para `world/countries.py::load_country_pack`
# (ADR 013 secc. 1/2/6 punto 4: la corrida puede cruzar de una epoca a la
# siguiente en la eleccion que cae dentro de la nueva epoca).
# ---------------------------------------------------------------------------


@dataclass
class EraOverlay:
    """Todo lo que `load_country_pack` necesita para que una corrida de
    Argentina use partidos/actores/lealtades de epoca en vez de los de
    Aurora (ADR 013 secc. 1/2/3).

    `parties` es la union (por indice de mes de la corrida) de las epocas
    que la corrida toca: para la PRIMERA epoca tocada trae sus partidos con
    los `seats` reales de `parties.json`; para epocas siguientes (cruzadas a
    mitad de corrida) trae sus partidos con `seats: 0` -- son "partidos
    nuevos" desde el punto de vista de esta corrida (ADR 013 secc. 1,
    literal), aunque ya existieran en la realidad antes del cruce.

    `loyalty_table.party_active_from`/`party_active_until` (indice de mes,
    1-based, ambos inclusive; ausente = sin limite de ese lado) es el
    mecanismo que hace el "cambio de epoca" y el "partido nuevo no existe
    hasta su fundacion" (ADR 013 secc. 5) una misma cosa: `world/elections.py
    ::compute_vote_intention` excluye de la utilidad/softmax a todo partido
    fuera de su ventana activa ese mes -- sin eso, no hace falta ningun
    cambio en `engine/simulation.py`: el `month` que ya recibe
    `run_election` (sin modificar su firma en el sitio de llamada de
    `_run_election`) alcanza."""

    active_era: Era | None
    parties: list[dict] | None
    loyalty_table: LoyaltyTable | None
    actors: dict[str, ActorSheet] | None
    governance_path: Path | None
    #: `{indice_de_mes: era_id}` de cada frontera de epoca que la corrida
    #: cruza (ADR 013 secc. 6 punto 4: "el JSONL registra `era_change`") --
    #: `world/elections.py::run_election` lo consulta con `month` (el mismo
    #: indice que ya recibe) para poner `ElectionResult.era_change`.
    era_boundaries: dict[int, str] = field(default_factory=dict)
    warning: str | None = None


def _load_era_loyalty_csv(era: Era) -> tuple[dict[tuple[str, str], float], dict[str, float]]:
    loyalty: dict[tuple[str, str], float] = {}
    turnout: dict[str, float] = {}
    path = era.dir / "cohorts_loyalty.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            loyalty[(row["cohort_id"], row["party_id"])] = float(row["loyalty"])
            turnout.setdefault(row["cohort_id"], float(row["turnout"]))
    return loyalty, turnout


def build_era_overlay(
    country_id: str, start: str, months: int, term_length: int = 48
) -> EraOverlay:
    """Arma el `EraOverlay` para una corrida de `months` meses desde `start`
    (ADR 013 secc. 1/3): la epoca que cubre `start`, mas cualquier epoca
    subsiguiente que la corrida cruce (ADR 013 secc. 6 punto 4).

    `term_length` (default 48, el mismo default que `world.config.Country`/
    `world/countries.py::term_length_months_for`): solo se usa para ubicar
    la ELECCION que cruza cada frontera (`_first_election_at_or_after`),
    para `LoyaltyTable.era_boundaries`/`ElectionResult.era_change` -- no
    cambia que partidos estan activos en ningun mes intermedio (ver
    docstring de `_first_election_at_or_after`)."""
    try:
        start_year, start_month = _parse_ym(start)
    except ValueError:
        return EraOverlay(None, None, None, None, None, {}, warning=f"--start invalido: {start!r}.")

    active = select_era(country_id, start)
    if active is None:
        warning = (
            f"No hay epoca de '{country_id}' que cubra '{start}' (epocas disponibles: "
            f"{[e.id for e in list_eras(country_id)] or '(ninguna)'}); se usan los partidos/"
            "actores/lealtades de Aurora."
        )
        return EraOverlay(None, None, None, None, None, {}, warning=warning)

    end_year, end_month = _advance_ym(start_year, start_month, months - 1)
    all_eras = list_eras(country_id)
    touched = [e for e in all_eras if e.start_year <= end_year and e.end_year >= start_year]
    touched.sort(key=lambda e: e.start_year)

    party_dicts: list[dict] = []
    loyalty = LoyaltyTable()
    boundaries: dict[int, str] = {}
    actors: dict[str, ActorSheet] | None = None
    governance_path: Path | None = None

    for i, era in enumerate(touched):
        raw_parties = load_era_parties(era)
        era_start_idx = _month_index(start_year, start_month, era.start_year, 1)
        if i == 0:
            window_from = 1
        else:
            window_from = max(era_start_idx, 1)
            boundaries[_first_election_at_or_after(window_from, term_length)] = era.id
        window_until: int | None = None
        if i + 1 < len(touched):
            nxt = touched[i + 1]
            nxt_idx = _month_index(start_year, start_month, nxt.start_year, 1)
            window_until = nxt_idx - 1

        for p in raw_parties:
            pid = p["id"]
            founded = p.get("founded")
            if founded is not None:
                f_year, f_month = (
                    (int(founded), 1) if isinstance(founded, int) else _parse_ym(str(founded))
                )
                founded_idx = _month_index(start_year, start_month, f_year, f_month)
                active_from = max(window_from, founded_idx)
            else:
                active_from = window_from
            loyalty.party_active_from[pid] = active_from
            if window_until is not None:
                loyalty.party_active_until[pid] = window_until
            bonus = p.get("outsider_bonus")
            if bonus:
                loyalty.party_outsider_bonus[pid] = float(bonus)
            #: "los partidos nuevos entran con seats 0" (ADR 013 secc. 1,
            #: literal): tanto los que la corrida arranca sin haber cruzado
            #: aun ninguna frontera (`i == 0`, `seats` reales del inicio de
            #: la corrida) como los de una epoca cruzada a mitad de corrida
            #: (`i > 0`, siempre 0 -- nunca tuvieron bancas EN ESTA
            #: corrida, aunque ya existieran en la realidad).
            seats = int(p.get("seats", 0)) if i == 0 else 0
            party_dicts.append(
                {
                    "id": pid,
                    "name": p["name"],
                    "seats": seats,
                    "economic": p["economic"],
                    "social": p["social"],
                    "in_government": bool(p.get("in_government", False)) if i == 0 else False,
                    "is_ally": False,
                    "coalition_weight": 1.0,
                    "discipline": float(p.get("discipline", 1.0)),
                }
            )

        era_loyalty, era_turnout = _load_era_loyalty_csv(era)
        loyalty.loyalty.update(era_loyalty)
        for cid, t in era_turnout.items():
            loyalty.turnout.setdefault(cid, t)

        if i == 0:
            actors = load_era_actors(era)
            governance_path = era_governance_path(era)

    #: `loyalty.era_boundaries` (no solo `EraOverlay.era_boundaries`) es lo
    #: que `world/elections.py::run_election` realmente consulta con
    #: `month` para `ElectionResult.era_change` -- `LoyaltyTable` es el
    #: unico de los dos objetos que efectivamente viaja hasta ahi (via
    #: `run(loyalty_table=...)`).
    loyalty.era_boundaries = dict(boundaries)

    return EraOverlay(
        active_era=active,
        parties=party_dicts,
        loyalty_table=loyalty,
        actors=actors,
        governance_path=governance_path,
        era_boundaries=boundaries,
        warning=None,
    )


# ---------------------------------------------------------------------------
# Estimacion inversa de lealtades (ADR 013 secc. 4): dados los shares
# nacionales reales de la eleccion de apertura de una epoca y la composicion
# de cohortes, resuelve la lealtad `loyalty_c,p` (UNIFORME por cohorte -- ver
# docstring de `estimate_loyalties` para por que) que reproduce esos shares
# bajo utilidad neutra (aprobacion 50, economia plana) con el mismo softmax
# y tau del motor (`world/elections.py::compute_vote_intention`/`TAU_SHARE`).
# ---------------------------------------------------------------------------


def _neutral_shares(
    cohorts: list[Cohort],
    party_ids: list[str],
    party_economic: dict[str, float],
    loyalty: dict[tuple[str, str], float],
    turnout: dict[str, float],
    tau: float,
    v_ideo: float,
    v_loy: float,
) -> dict[str, float]:
    """Agregado nacional (sin ruido: `world/elections.py::aggregate_vote`
    sin el paso `N(0, VOTE_NOISE_STD)`, que por diseno es una perturbacion
    chica pensada para UNA eleccion jugada, no para calibrar contra ella)
    bajo utilidad neutra: solo `v_ideo` (afinidad ideologica fija por
    cohorte) y `v_loy` (la lealtad que se esta resolviendo) pesan -- con
    `government_approval=50`/deltas economicos en 0, `v_econ`/`v_appr` dan
    0 exacto (secc. 2.2 del ADR 006, `econ_vote`/`(approval-50)/50`), y sin
    `memory_store`/`campaign_state`/`regional_bonus` los otros tres
    terminos tambien son 0 -- ningun partido de la epoca de apertura tiene
    `outsider_bonus` (ADR 013 secc. 5: el termino solo aplica a partidos NO
    fundados aun, que ya estan excluidos de `party_ids` en la eleccion de
    apertura por construccion)."""
    raw = dict.fromkeys(party_ids, 0.0)
    for c in cohorts:
        util = {
            pid: v_ideo * (1.0 - abs(c.econ_pref - party_economic[pid])) + v_loy * loyalty[(c.id, pid)]
            for pid in party_ids
        }
        m = max(util.values())
        exps = {pid: math.exp((u - m) / tau) for pid, u in util.items()}
        total = sum(exps.values()) or 1.0
        t = turnout.get(c.id, DEFAULT_TURNOUT)
        for pid in party_ids:
            raw[pid] += c.pop_share * t * (exps[pid] / total)
    total_raw = sum(raw.values()) or 1.0
    return {pid: raw[pid] / total_raw for pid in party_ids}


def estimate_loyalties(
    cohorts: list[Cohort],
    party_ids: list[str],
    party_economic: dict[str, float],
    targets: dict[str, float],
    turnout: dict[str, float] | None = None,
    *,
    tau: float = TAU_SHARE,
    v_ideo: float = WEIGHTS["v_ideo"],
    v_loy: float = WEIGHTS["v_loy"],
    lo: float = -5.0,
    hi: float = 5.0,
    rounds: int = 40,
    bisection_iters: int = 40,
) -> dict[tuple[str, str], float]:
    """Procedimiento inverso de ADR 013 secc. 4: `targets` (`{party_id:
    share nacional real [0, 1]}`, ya renormalizado sobre `party_ids` -- ver
    `scripts/build_argentina_eras.py` para como se arma desde
    `politics/sources/electorAr_presi/*.csv`) -> lealtad por (cohorte,
    partido) que reproduce esos shares con `_neutral_shares` dentro de
    tolerancia.

    Devuelve el MISMO valor de lealtad para todas las cohortes de un partido
    dado (documentado, no un artefacto de implementacion): los shares
    nacionales de `electorAr_presi` no traen desagregacion por cohorte
    (serian necesarios datos de boca de urna/encuesta por segmento
    socioeconomico que no estan descargados en este entorno), asi que no
    hay informacion para diferenciar `loyalty_c,p` entre cohortes de un
    mismo partido -- la UNICA diferenciacion por cohorte que el modelo
    puede justificar con los datos disponibles es la afinidad ideologica
    (`v_ideo`, ya diferenciada por `econ_pref_c` en `cohorts.csv`), que la
    resolucion deja fija y resuelve la lealtad alrededor de ella. Convergea
    por coordenadas (Gauss-Seidel: un partido a la vez, biseccion sobre su
    lealtad uniforme mientras los demas quedan fijos, en `rounds` pasadas)
    -- el share agregado de un partido es monotono creciente en su propia
    lealtad (mismo argumento que la monotonia del softmax est'andar), asi
    que cada biseccion interna converge; las pasadas exteriores convergen
    porque el punto fijo de Gauss-Seidel para un sistema de softmax con
    peso positivo en la diagonal (aca, cada partido "empuja" su propio
    share con `v_loy`) es unico y atractivo en la practica -- confirmado
    empiricamente (ver `tests/test_eras_argentina.py`, error < tolerancia
    de biseccion en las 3 epocas)."""
    turnout = turnout or {}
    loyalty: dict[tuple[str, str], float] = {(c.id, pid): 0.0 for c in cohorts for pid in party_ids}
    for _ in range(rounds):
        for pid in party_ids:
            party_lo, party_hi = lo, hi
            for _b in range(bisection_iters):
                mid = (party_lo + party_hi) / 2.0
                for c in cohorts:
                    loyalty[(c.id, pid)] = mid
                shares = _neutral_shares(
                    cohorts, party_ids, party_economic, loyalty, turnout, tau, v_ideo, v_loy
                )
                if shares[pid] < targets[pid]:
                    party_lo = mid
                else:
                    party_hi = mid
            final = (party_lo + party_hi) / 2.0
            for c in cohorts:
                loyalty[(c.id, pid)] = final
    return loyalty


def reproduction_errors(
    cohorts: list[Cohort],
    party_ids: list[str],
    party_economic: dict[str, float],
    loyalty: dict[tuple[str, str], float],
    targets: dict[str, float],
    turnout: dict[str, float] | None = None,
    *,
    tau: float = TAU_SHARE,
    v_ideo: float = WEIGHTS["v_ideo"],
    v_loy: float = WEIGHTS["v_loy"],
) -> dict[str, float]:
    """`{party_id: error en puntos porcentuales}` de `loyalty` contra
    `targets` bajo utilidad neutra (ADR 013 secc. 4/6 punto 2: "se
    reproduce +-3 pp"). Reusa `_neutral_shares` -- lo mismo que
    `estimate_loyalties` optimiza, en formato de reporte."""
    shares = _neutral_shares(
        cohorts, party_ids, party_economic, loyalty, turnout or {}, tau, v_ideo, v_loy
    )
    return {pid: (shares[pid] - targets[pid]) * 100.0 for pid in party_ids}
