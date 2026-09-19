"""Validacion historica de Argentina (A4, ADR 011 secc. 8).

Tres pruebas con hipotesis REGISTRADAS ANTES de correr (`HYPOTHESES`, texto
literal de la tabla del ADR 011 secc. 8 -- hay un test que lo compara
caracter a caracter contra el markdown del ADR) mas un control con los
coeficientes SIN CALIBRAR de Aurora:

- `V1` 1988-06 + 24 meses, solo exogenas reales, sin ningun shock forzado
  (`hyperinflation_regime` no se fuerza NUNCA, ADR 011 secc. 4).
- `V2` 1998-01 + 54 meses, `fx_regime = peg`, crisis internacional 1998-99
  forzada desde `politics/shocks_calendar.csv`.
- `V3` 2016-01 + 96 meses, sequia 2018 / pandemia 2020 / sequia 2023
  forzadas desde el mismo calendario.
- `C` = las tres anteriores con los coeficientes de Aurora (brazo `aurora`
  de cada prueba), para medir el "valor" de la calibracion.

Protocolo (PLAN_ARGENTINA.md secc. 0.3 y 4): antes de correr una sola
simulacion se escribe `registration.json` en el directorio de salida con
(a) la hipotesis literal de cada prueba, (b) los shocks forzados PEDIDOS por
el ADR y los que el calendario real permite aplicar EFECTIVAMENTE, y (c) la
procedencia (`source`/`proxy`/`assumed`) de cada variable del estado
inicial. Recien despues se corre; el reporte no puede "elegir" la hipotesis
a posteriori.

Los shocks ALEATORIOS de Aurora (`shocks.json`) siguen activos, igual que en
cualquier `republica run`: la lista de shocks forzados no es la lista de
shocks que ocurrieron. El reporte incluye los aleatorios observados.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from republica.calibration.run import HONESTY_SENTENCE
from republica.engine.narrate import annualized_inflation
from republica.engine.policy import PassivePolicy
from republica.engine.simulation import History
from republica.engine.simulation import run as run_simulation
from republica.world.countries import (
    CountryPack,
    country_pack_dir,
    historical_exogenous_series,
    load_country_pack,
)
from republica.world.economy import merge_structural_coefficients

#: Hipotesis de la tabla de ADR 011 secc. 8, columna "Hipotesis", LITERAL.
#: `tests/test_validation_argentina.py::test_hypotheses_match_adr_text` las
#: compara caracter a caracter contra `docs/ADR_011_country_pack_argentina.md`:
#: si alguien edita el ADR despues de correr A4, el test falla y obliga a
#: re-registrar (no se puede reescribir la hipotesis para que de). `V4` (A5,
#: ADR 012 secc. 6) NO viene de esa tabla -- es la hipotesis registrada en
#: la tarea de recalibracion misma, textual, y por eso queda FUERA del
#: alcance de ese test (que solo itera sobre las filas que encuentra en el
#: ADR 011, `V1`/`V2`/`V3`/`C`).
HYPOTHESES: dict[str, str] = {
    "V1": "el modelo entra en `hyperinflation` en 12–24 meses en > 50 % de semillas",
    "V2": "`sovereign_default` o `collapse` en 36–54 meses en > 50 %",
    "V3": "inflación anual final > 80 % en la mediana y el oficialismo pierde en 2019 y 2023",
    "V4": "el oficialismo pierde en > 70 % de semillas y la inflación anual final mediana "
    "supera 100 %",
    "C": "Aurora sin calibrar falla al menos una de las tres",
}

#: Columna "Metrica" de la misma tabla, tambien literal (mismo test).
METRICS: dict[str, str] = {
    "V1": "fracción de semillas, mes mediano",
    "V2": "idem + trayectoria de reservas vs real",
    "V3": "error de inflación, aciertos electorales",
    "V4": "fracción de semillas con derrota electoral, inflación anual final mediana",
    "C": 'la diferencia con el calibrado es el "valor" de la calibración',
}

#: Columna "Shocks forzados" de la misma tabla, tambien literal.
ADR_FORCED_SHOCKS: dict[str, str] = {
    "V1": "solo exógenos (commodities, mundo) — **no** se fuerza la hiper",
    "V2": "crisis internacional 1998–99 (Rusia, Brasil)",
    "V3": "sequía 2018, pandemia 2020, sequía 2023",
    "V4": "pandemia 2020, sequía 2023, FMI 2022 (todos exógenos)",
    "C": "los mismos",
}

#: Pruebas que se corren por default (`republica validate` sin `--tests`):
#: V4 (A5, ADR 012 secc. 6) queda AFUERA -- depende de que el paquete traiga
#: partidos argentinos por epoca (ADR 013, en curso en paralelo, ver
#: `_v4_blocked_reason`). Pedirla explicito con `--tests V4` la intenta
#: igual (y la salta con aviso si el paquete todavia no trae esa epoca)."""
DEFAULT_TEST_IDS: tuple[str, ...] = ("V1", "V2", "V3")

#: Brazos de cada prueba: `calibrated` usa `calibration/<run_id>/`,
#: `aurora` los coeficientes de `country.json` sin tocar (la fila C del ADR).
ARMS: tuple[str, str] = ("calibrated", "aurora")

ARM_LABELS = {"calibrated": "calibrado", "aurora": "Aurora sin calibrar"}


@dataclass(frozen=True)
class ShockRequest:
    """Un shock que el ADR pide forzar, como CONSULTA al calendario real
    (`politics/shocks_calendar.csv`), no como una fila inventada: `shock_id`
    dentro de la ventana `[date_from, date_to]` (`YYYY-MM` inclusive). Si el
    calendario no tiene ninguna fila que matchee, NO se fuerza nada y el
    faltante queda registrado en `registration.json` y en el reporte (regla
    de honestidad: ningun dato historico se inventa, PLAN_ARGENTINA.md
    secc. 0.1)."""

    shock_id: str
    date_from: str
    date_to: str
    label: str


@dataclass(frozen=True)
class ValidationTest:
    test_id: str
    title: str
    start: str
    months: int
    fx_regime: str | None
    shock_requests: tuple[ShockRequest, ...]
    #: Serie real contra la que se compara la trayectoria del grafico.
    real_series: str
    real_series_label: str
    y_label: str


TESTS: tuple[ValidationTest, ...] = (
    ValidationTest(
        test_id="V1",
        title="V1 1988→1990: ¿emerge la hiperinflación?",
        start="1988-06",
        months=24,
        fx_regime=None,
        shock_requests=(),
        real_series="inflation_monthly_implied",
        real_series_label="IPC mensual implícito de la variación anual (Banco Mundial)",
        y_label="inflación mensual (%)",
    ),
    ValidationTest(
        test_id="V2",
        title="V2 1998→2002: ¿colapso con convertibilidad rígida?",
        start="1998-01",
        months=54,
        fx_regime="peg",
        shock_requests=(
            ShockRequest(
                shock_id="international_crisis",
                date_from="1998-01",
                date_to="1999-12",
                label="crisis internacional 1998–99 (Rusia, Brasil)",
            ),
        ),
        real_series="reserves_monthly",
        real_series_label="reservas del BCRA (USD M, fin de mes)",
        y_label="reservas (USD M)",
    ),
    ValidationTest(
        test_id="V3",
        title="V3 2016→2023: ¿se acelera la inflación y pierde el oficialismo?",
        start="2016-01",
        months=96,
        fx_regime=None,
        shock_requests=(
            ShockRequest("drought", "2018-01", "2018-12", "sequía 2018"),
            ShockRequest("epidemic", "2020-01", "2020-12", "pandemia 2020"),
            ShockRequest("drought", "2023-01", "2023-12", "sequía 2023"),
        ),
        real_series="inflation_annual",
        real_series_label="IPC, variación anual (Banco Mundial, serie empalmada)",
        y_label="inflación anualizada (%)",
    ),
    #: V4 (A5, ADR 012 secc. 6): NO se corre todavia -- depende de ADR 013
    #: (partidos argentinos por epoca), en curso en paralelo. Definicion
    #: registrada AHORA, antes de tener resultados (mismo protocolo que
    #: V1-V3), para que `--tests V4` no pueda "ajustarse" a los resultados
    #: de A6/A7 en curso; `run_validation` la salta con aviso si el paquete
    #: no trae epoca de partidos para `start` (`_v4_blocked_reason`).
    ValidationTest(
        test_id="V4",
        title="V4 2019-12→2023-12: ¿pierde el oficialismo con partidos argentinos?",
        start="2019-12",
        months=48,
        fx_regime=None,  # "auto" (ADR 012 deliverable 5): control desde 2019-09 (fx_regimes.csv)
        shock_requests=(
            ShockRequest("epidemic", "2020-01", "2020-12", "pandemia 2020"),
            ShockRequest("drought", "2023-01", "2023-12", "sequía 2023"),
            ShockRequest("imf_program", "2022-01", "2022-12", "FMI 2022"),
        ),
        real_series="inflation_annual",
        real_series_label="IPC, variación anual (Banco Mundial, serie empalmada)",
        y_label="inflación anualizada (%)",
    ),
)

TESTS_BY_ID = {t.test_id: t for t in TESTS}


# --------------------------------------------------------------------------
# Calendario de shocks: lo pedido por el ADR vs. lo que el calendario tiene
# --------------------------------------------------------------------------


def _month_index(start: str, date: str) -> int:
    sy, sm = int(start[:4]), int(start[5:7])
    y, m = int(date[:4]), int(date[5:7])
    return (y - sy) * 12 + (m - sm) + 1


def month_date(start: str, month_index: int) -> str:
    """`month_index` 1 == `start` (mismo criterio que
    `engine/simulation.py::_format_date`)."""
    sy, sm = int(start[:4]), int(start[5:7])
    total = (sm - 1) + (month_index - 1)
    return f"{sy + total // 12:04d}-{total % 12 + 1:02d}"


#: Shocks ENDOGENOS (A5, ADR 012 secc. 6): lo que el motor deberia producir
#: por su propia dinamica dado el estado inicial y los shocks EXOGENOS,
#: no algo que se le fuerza desde afuera -- forzarlos convertiria la prueba
#: en "reproduce 1989 porque se le forzo 1989", exactamente lo que
#: `PLAN_ARGENTINA.md` #0.3 prohibe ("no predijo nada"). `resolve_forced_
#: shocks` nunca los aplica, sin importar que pida `ValidationTest.
#: shock_requests` (defensivo: hoy ningun `ShockRequest` de `TESTS` pide
#: uno de estos, pero la lista existe para que un `ShockRequest` futuro mal
#: escrito no los cuele en silencio). `coup`/`hyperinflation_regime` no son
#: `shock_id` del catalogo (`hyperinflation_regime` SI lo es, ver
#: `data/countries/argentina/shocks.json`); se incluyen los cuatro que
#: podrian confundirse con "la crisis que se esta prediciendo" en V1/V2.
ENDOGENOUS_SHOCKS: frozenset[str] = frozenset(
    {"hyperinflation_regime", "sovereign_default", "banking_crisis", "coup"}
)


def _read_shocks_calendar(pack_dir: Path) -> list[dict[str, str]]:
    path = pack_dir / "politics" / "shocks_calendar.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@dataclass
class ForcedShockPlan:
    """Lo que se le pasa a `run(forced_shocks=...)` mas la traza de como se
    llego a eso (para `registration.json` y el reporte)."""

    forced: dict[int, list[str]] = field(default_factory=dict)
    requested: list[dict] = field(default_factory=list)
    #: `shock_id` que `test.shock_requests` pidio pero `resolve_forced_
    #: shocks` REHUSO forzar por estar en `ENDOGENOUS_SHOCKS` (A5, ADR 012
    #: secc. 6) -- vacia salvo que un `ShockRequest` futuro pida uno.
    excluded_endogenous: list[str] = field(default_factory=list)

    @property
    def applied_rows(self) -> list[dict]:
        return [row for req in self.requested for row in req["matched"]]

    @property
    def unmatched(self) -> list[dict]:
        return [req for req in self.requested if not req["matched"]]


def resolve_forced_shocks(pack_dir: Path, test: ValidationTest, months: int) -> ForcedShockPlan:
    """Traduce los `ShockRequest` del ADR a `{mes: [shock_id]}` consultando
    `politics/shocks_calendar.csv`. Cada pedido queda registrado con las
    filas del calendario que lo satisfacen (puede ser ninguna). `shock_id`
    en `ENDOGENOUS_SHOCKS` (A5, ADR 012 secc. 6) NUNCA se fuerza -- eso es
    lo que la prueba mide, no un dato que se le regale al modelo; queda
    registrado en `plan.excluded_endogenous`/`registration.json` para que
    el reporte diga explicitamente que se exlcuyo."""
    rows = _read_shocks_calendar(pack_dir)
    plan = ForcedShockPlan()
    excluded: list[str] = []
    for req in test.shock_requests:
        if req.shock_id in ENDOGENOUS_SHOCKS:
            excluded.append(req.shock_id)
            plan.requested.append(
                {
                    "shock_id": req.shock_id,
                    "label": req.label,
                    "window": f"{req.date_from}:{req.date_to}",
                    "matched": [],
                    "excluded_endogenous": True,
                }
            )
            continue
        matched: list[dict] = []
        for row in rows:
            if row["shock_id"] != req.shock_id:
                continue
            date = row["date"][:7]
            if not (req.date_from <= date <= req.date_to):
                continue
            idx = _month_index(test.start, date)
            if not (1 <= idx <= months):
                continue
            matched.append(
                {
                    "shock_id": row["shock_id"],
                    "date": date,
                    "month_index": idx,
                    "title": row.get("title", ""),
                    "duration_months": row.get("duration_months", ""),
                }
            )
            plan.forced.setdefault(idx, []).append(row["shock_id"])
        plan.requested.append(
            {
                "shock_id": req.shock_id,
                "label": req.label,
                "window": f"{req.date_from}:{req.date_to}",
                "matched": matched,
            }
        )
    plan.excluded_endogenous = excluded
    return plan


# --------------------------------------------------------------------------
# Corrida de una prueba
# --------------------------------------------------------------------------


@dataclass
class SeedRun:
    """Lo que el analisis necesita de UNA corrida (no se guarda el JSONL
    completo de 300 corridas: el reporte usa estas series)."""

    seed: int
    outcome: str
    months_run: int
    dates: list[str]
    inflation_monthly: list[float]
    reserves: list[float]
    political_stability: list[float]
    government_approval: list[float]
    default_active_months: list[int]
    elections: list[dict]
    random_shocks: list[str]

    @property
    def inflation_annual_final(self) -> float:
        return annualized_inflation(self.inflation_monthly[-1])


def _history_to_seed_run(seed: int, history: History, forced_ids: set[str]) -> SeedRun:
    recs = history.records
    return SeedRun(
        seed=seed,
        outcome=history.outcome,
        months_run=len(recs),
        dates=[r.date for r in recs],
        inflation_monthly=[r.state["inflation"] for r in recs],
        reserves=[r.state["reserves"] for r in recs],
        political_stability=[r.state["political_stability"] for r in recs],
        government_approval=[r.state["government_approval"] for r in recs],
        default_active_months=[
            r.month_index for r in recs if "sovereign_default" in r.shocks_active
        ],
        elections=[
            {
                "month": e.month,
                "date": recs[e.month - 1].date if e.month <= len(recs) else "",
                "outcome_type": e.outcome_type,
                "winner": e.winner,
                "incumbent_party": e.incumbent_party,
            }
            for e in history.election_records
        ],
        random_shocks=sorted({s for r in recs for s in r.shocks_new if s not in forced_ids}),
    )


def _load_pack(test: ValidationTest, months: int, regime_transitions: bool = False) -> CountryPack:
    """`regime_transitions` (ADR 015, default `False`): prende el modelo de
    riesgo endogeno del regimen. Apagado, el paquete sale identico a A4."""
    return load_country_pack(
        "argentina",
        test.start,
        months,
        regime_mode="auto",
        regime_transitions=regime_transitions,
    )


def run_test_arm(
    test: ValidationTest,
    arm: str,
    pack: CountryPack,
    plan: ForcedShockPlan,
    months: int,
    seeds: int,
    seed_base: int,
    calibration_run_id: str,
    legitimacy_floor: bool | None = None,
) -> list[SeedRun]:
    """Corre `seeds` semillas de `test` con el brazo `arm`
    (`calibrated`/`aurora`). Todo lo demas (estado inicial real, calendario
    de regimen, exogenas reales, features de `country.json`) es identico
    entre brazos: la UNICA diferencia es el vector de coeficientes.

    A5 (ADR 012 secc. 6): si `country.features.macro_regime` esta prendido
    (Argentina, desde ADR 012), ambos brazos corren con `macro_coefficients`
    -- `"aurora"` con el macro del paquete (`pack.macro_coefficients`, ADR
    012 sin calibrar, mismo criterio que `cli.py`'s `republica run` sin
    `--calibration`), `"calibrated"` con el macro de `calibration_run_id`
    SI esa calibracion lo trae (`load_calibrated_country` devuelve `None`
    para una calibracion vieja sin macro, p.ej. `a3_main`: en ese caso el
    brazo `"calibrated"` queda sin macro, igual que antes de A5). El
    regimen cambiario efectivo (`fx_regime`, ADR 012 secc. 3) se resuelve
    `test.fx_regime` (V2 pide `peg`) o, si la prueba no fuerza uno,
    `pack.fx_regime_auto` (el regimen REAL de `test.start` segun
    `fx_regimes.csv`, deliverable 5 del ADR) -- mas fiel que el default fijo
    de `BimonetaryCoefficients.fx_regime_default` que se usaba antes de A5.

    ADR 013 secc. 1/3 (integrado en paralelo, HEAD `a2e0b6a`): si el
    paquete resolvio una epoca de partidos para `test.start`
    (`pack.era.parties is not None` -- hoy cubre las 4 pruebas: 1983-2001
    para V1/V2, 2015-2023 para V3/V4), sus actores/lealtades/gobernanza
    reemplazan a los de Aurora, MISMO criterio que `cli.py`'s `republica
    run` (`era_actors`/`era_loyalty_table`/`era_gov_overrides`): sin esto,
    `country.parties` ya saldria con los partidos de la epoca (via
    `merged/parties.json`, hecho por `load_country_pack`) pero la eleccion
    usaria una `LoyaltyTable` sin ninguna entrada para esos partidos
    (lealtad 0 para todos) y el `ActorEngine` seguiria con los 29 actores
    de Aurora -- el mismo bug que el fix de `cli.py` corrigio para
    `republica run`.

    ADR 016: `legitimacy_floor` (default `None`) se pasa tal cual a `run()`,
    que con `None` lo resuelve desde `country.features["legitimacy_floor"]`
    (Argentina: prendido). Existe como parametro explicito para que
    `tests/test_collapse_recovery.py` pueda medir el MISMO brazo con y sin
    el piso sin tocar `country.json`."""
    from dataclasses import replace as dc_replace

    country = pack.country
    bimonetary = pack.bimonetary_coefficients
    macro_active = country.features.get("macro_regime", False)
    macro = pack.macro_coefficients if macro_active else None
    coefficients_by_fx_regime = None
    if arm == "calibrated":
        from republica.calibration.run import (
            load_calibrated_country,
            load_calibrated_vectors_by_group,
        )

        # ADR 017 secc. 3.5: con una calibracion `--by-regime`, el vector se
        # elige por el `fx_regime` real de la fecha de arranque de la
        # prueba; con el formato viejo el `start` se ignora y sale el unico
        # vector, igual que siempre.
        coeff, bimonetary, calibrated_macro = load_calibrated_country(
            "argentina", calibration_run_id, start=test.start
        )
        country = country.model_copy(update={"coefficients": coeff})
        if macro_active and calibrated_macro is not None:
            # ADR 016: los `lf_*` son estructurales y NO estan en el vector
            # calibrado (`coefficients.json` de `a5b_macro` guarda 60 claves,
            # ninguna `lf_*`), asi que se toman del paquete de pais en vez de
            # los defaults de la clase. Ver `world/economy.py::
            # LEGITIMACY_FIELDS`.
            macro = merge_structural_coefficients(calibrated_macro, pack.macro_coefficients)
        # ADR 017 secc. 3.6: cambio de vector en caliente si el regimen
        # simulado sale de su grupo (`None` con el formato viejo).
        coefficients_by_fx_regime = load_calibrated_vectors_by_group(calibration_run_id)
    if test.fx_regime:
        bimonetary = dc_replace(bimonetary, fx_regime_default=test.fx_regime)
    resolved_fx_regime = test.fx_regime or pack.fx_regime_auto

    era_actors = None
    era_loyalty_table = None
    era_gov_overrides: dict[str, str] = {}
    if pack.era is not None and pack.era.parties is not None:
        era_actors = pack.era.actors
        era_loyalty_table = pack.era.loyalty_table
        if pack.era.governance_path is not None and pack.era.governance_path.exists():
            from republica.world.eras import era_governance_overrides

            era_gov_overrides = era_governance_overrides(pack.era.governance_path)

    exogenous = historical_exogenous_series(
        pack.pack_dir, int(test.start[:4]), int(test.start[5:7]), months
    )
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    features = country.features
    forced_ids = {sid for ids in plan.forced.values() for sid in ids}

    runs: list[SeedRun] = []
    for i in range(seeds):
        seed = seed_base + i
        history = run_simulation(
            seed=seed,
            months=months,
            policy_rule=policy_rule,
            forced_shocks={k: list(v) for k, v in plan.forced.items()} or None,
            country=country,
            actors_enabled=features.get("actors", True),
            actors=era_actors,
            congress_enabled=features.get("congress", True),
            negotiation_enabled=features.get("negotiation", True),
            cohorts_enabled=features.get("cohorts", True),
            media_enabled=features.get("media", True),
            memory_enabled=features.get("memory", True),
            elections_enabled=features.get("elections", True),
            loyalty_table=era_loyalty_table,
            governance_overrides=era_gov_overrides or None,
            regime_calendar=pack.regime_calendar,
            bimonetary_coefficients=bimonetary,
            historical_exogenous=exogenous,
            macro_coefficients=macro,
            macro_x0=pack.macro_x0 if macro is not None else None,
            macro_m0=pack.macro_m0 if macro is not None else None,
            fx_regime=resolved_fx_regime if macro is not None else test.fx_regime,
            coefficients_by_fx_regime=coefficients_by_fx_regime,
            legitimacy_floor=legitimacy_floor,
        )
        runs.append(_history_to_seed_run(seed, history, forced_ids))
    return runs


# --------------------------------------------------------------------------
# Metricas y bootstrap
# --------------------------------------------------------------------------


def bootstrap_ci(
    values: list[float],
    stat,
    *,
    resamples: int = 2000,
    seed: int = 20240501,
    level: float = 0.95,
) -> tuple[float | None, float | None]:
    """IC percentil por bootstrap sobre las SEMILLAS (remuestreo con
    reemplazo del vector de resultados por semilla). Devuelve `(None, None)`
    si no hay datos suficientes."""
    clean = [v for v in values if v is not None]
    if not clean:
        return (None, None)
    rng = random.Random(seed)
    n = len(clean)
    stats: list[float] = []
    for _ in range(resamples):
        sample = [clean[rng.randrange(n)] for _ in range(n)]
        try:
            stats.append(float(stat(sample)))
        except (statistics.StatisticsError, ValueError, ZeroDivisionError):
            continue
    if not stats:
        return (None, None)
    stats.sort()
    lo_i = int((1.0 - level) / 2.0 * len(stats))
    hi_i = min(len(stats) - 1, int((1.0 + level) / 2.0 * len(stats)))
    return (stats[lo_i], stats[hi_i])


def _fraction(flags: list[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


def _median_or_none(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def metrics_v1(runs: list[SeedRun], months: int, resamples: int) -> dict:
    """ADR 011 secc. 8, V1: fraccion de semillas que entran en
    `hyperinflation` y mes mediano. El motor TERMINA la corrida cuando
    dispara `hyperinflation` (`world/events.py::check_termination`), asi que
    el mes del evento es el ultimo mes simulado."""
    hyper = [r.outcome == "hyperinflation" for r in runs]
    months_hyper = [float(r.months_run) for r in runs if r.outcome == "hyperinflation"]
    frac = _fraction(hyper)
    lo, hi = bootstrap_ci([1.0 if h else 0.0 for h in hyper], statistics.mean, resamples=resamples)
    m_lo, m_hi = bootstrap_ci(months_hyper, statistics.median, resamples=resamples)
    return {
        "hyperinflation_fraction": frac,
        "hyperinflation_fraction_ci": [lo, hi],
        "hyperinflation_median_month": _median_or_none(months_hyper),
        "hyperinflation_median_month_ci": [m_lo, m_hi],
        "n_hyperinflation": len(months_hyper),
        "outcomes": _outcome_counts(runs),
        "inflation_monthly_final_median": statistics.median(
            [r.inflation_monthly[-1] for r in runs]
        ),
        "inflation_annual_final_median": statistics.median(
            [r.inflation_annual_final for r in runs]
        ),
        "passes": frac > 0.5,
    }


def metrics_v2(runs: list[SeedRun], months: int, resamples: int, real: dict[str, float]) -> dict:
    """ADR 011 secc. 8, V2: `sovereign_default` o `collapse` en los meses
    36-54, mas el RMSE de la trayectoria de reservas contra la serie real.

    `sovereign_default` NO es un `outcome` del motor (los outcomes son
    `survived/collapse/hyperinflation/reelected/defeated`): es un SHOCK, que
    en esta corrida solo puede activarse por el disparo ENDOGENO del bloque
    bimonetario (`default_risk >= default_risk_threshold`), porque el
    calendario de 1998-2002 no fuerza ninguno."""
    lo_m, hi_m = 36, min(54, months)
    window = range(lo_m, hi_m + 1) if hi_m >= lo_m else range(0)
    flags: list[bool] = []
    for r in runs:
        defaulted = any(m in window for m in r.default_active_months)
        collapsed = r.outcome == "collapse" and r.months_run in window
        flags.append(defaulted or collapsed)
    frac = _fraction(flags)
    lo, hi = bootstrap_ci([1.0 if f else 0.0 for f in flags], statistics.mean, resamples=resamples)

    rmses: list[float] = []
    for r in runs:
        errs = [(r.reserves[i] - real[d]) ** 2 for i, d in enumerate(r.dates) if d in real]
        if errs:
            rmses.append((sum(errs) / len(errs)) ** 0.5)
    r_lo, r_hi = bootstrap_ci(rmses, statistics.median, resamples=resamples)

    # Baseline ingenuo: reservas constantes en el nivel real del mes de
    # arranque (persistencia), el mismo criterio de baseline que A3.
    base_rmse = None
    if runs and real:
        d0 = runs[0].dates[0]
        if d0 in real:
            errs = [(real[d0] - real[d]) ** 2 for d in runs[0].dates if d in real]
            if errs:
                base_rmse = (sum(errs) / len(errs)) ** 0.5

    return {
        "default_or_collapse_fraction": frac,
        "default_or_collapse_fraction_ci": [lo, hi],
        "window_months": [lo_m, hi_m] if hi_m >= lo_m else [],
        "window_empty": hi_m < lo_m,
        "n_default": sum(1 for r in runs if any(m in window for m in r.default_active_months)),
        "n_collapse_in_window": sum(
            1 for r in runs if r.outcome == "collapse" and r.months_run in window
        ),
        "outcomes": _outcome_counts(runs),
        "reserves_rmse_median": _median_or_none(rmses),
        "reserves_rmse_ci": [r_lo, r_hi],
        "reserves_rmse_persistence": base_rmse,
        "passes": frac > 0.5,
    }


#: Elecciones reales del periodo de V3 y su resultado (hecho publico:
#: 2019 Macri pierde ante Fernandez, 2023 Massa -- oficialismo -- pierde
#: ante Milei). El motor pone sus elecciones en multiplos de `term_length`
#: desde `--start` (ADR 011, Notas de implementacion A2: no calza las fechas
#: reales de octubre), asi que con `--start 2016-01` y mandato de 4 años
#: caen en 2019-12 y 2023-12.
V3_REAL_ELECTIONS: dict[str, str] = {"2019-12": "defeated", "2023-12": "defeated"}


def metrics_v3(runs: list[SeedRun], months: int, resamples: int) -> dict:
    """ADR 011 secc. 8, V3: mediana de la inflacion anualizada final y
    acierto electoral en 2019 y 2023."""
    finals = [r.inflation_annual_final for r in runs]
    med = statistics.median(finals)
    lo, hi = bootstrap_ci(finals, statistics.median, resamples=resamples)

    elections: dict[str, dict] = {}
    for date, real_outcome in V3_REAL_ELECTIONS.items():
        held = [r for r in runs if any(e["date"] == date for e in r.elections)]
        hits = [
            any(e["date"] == date and e["outcome_type"] == real_outcome for e in r.elections)
            for r in runs
        ]
        frac = _fraction(hits)
        e_lo, e_hi = bootstrap_ci(
            [1.0 if h else 0.0 for h in hits], statistics.mean, resamples=resamples
        )
        elections[date] = {
            "real_outcome": real_outcome,
            "n_held": len(held),
            "hit_fraction": frac,
            "hit_fraction_ci": [e_lo, e_hi],
            "passes": frac > 0.5,
        }

    inflation_ok = med > 80.0
    elections_ok = all(e["passes"] for e in elections.values())
    return {
        "inflation_annual_final_median": med,
        "inflation_annual_final_ci": [lo, hi],
        "inflation_threshold": 80.0,
        "inflation_passes": inflation_ok,
        "elections": elections,
        "outcomes": _outcome_counts(runs),
        "median_months_run": statistics.median([float(r.months_run) for r in runs]),
        "passes": inflation_ok and elections_ok,
    }


def metrics_v4(runs: list[SeedRun], months: int, resamples: int) -> dict:
    """A5 (ADR 012 secc. 6), V4 (definicion registrada, NO se corre todavia
    -- ver `TESTS`/`_v4_block_reason`): el oficialismo pierde en > 70 % de
    semillas y la inflacion anual final mediana supera 100 %. A diferencia
    de `metrics_v3` (que ata el acierto a DOS fechas nominales fijas,
    `V3_REAL_ELECTIONS`), aca se busca CUALQUIER eleccion dentro de la
    ventana con `outcome_type == "defeated"` -- V4 cubre un solo mandato
    (48 meses desde una asuncion de diciembre), asi que se espera una sola
    eleccion de fin de mandato, pero atarse a una fecha nominal exacta
    (`month_date` da 2023-11, no 2023-12, para el mes 48 desde 2019-12) es
    mas fragil que solo preguntar si HUBO una derrota."""
    finals = [r.inflation_annual_final for r in runs]
    med = statistics.median(finals)
    lo, hi = bootstrap_ci(finals, statistics.median, resamples=resamples)
    hits = [any(e["outcome_type"] == "defeated" for e in r.elections) for r in runs]
    frac = _fraction(hits)
    e_lo, e_hi = bootstrap_ci(
        [1.0 if h else 0.0 for h in hits], statistics.mean, resamples=resamples
    )
    inflation_ok = med > 100.0
    election_ok = frac > 0.7
    return {
        "inflation_annual_final_median": med,
        "inflation_annual_final_ci": [lo, hi],
        "inflation_threshold": 100.0,
        "inflation_passes": inflation_ok,
        "election_defeat_fraction": frac,
        "election_defeat_fraction_ci": [e_lo, e_hi],
        "election_threshold": 0.7,
        "election_passes": election_ok,
        "outcomes": _outcome_counts(runs),
        "median_months_run": statistics.median([float(r.months_run) for r in runs]),
        "passes": inflation_ok and election_ok,
    }


def _outcome_counts(runs: list[SeedRun]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in runs:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    return dict(sorted(counts.items()))


# --------------------------------------------------------------------------
# Series reales
# --------------------------------------------------------------------------


def _load_history_csv(pack_dir: Path, name: str) -> list[tuple[str, float]]:
    path = pack_dir / "history" / f"{name}.csv"
    if not path.exists():
        return []
    out: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append((row["date"][:7], float(row["value"])))
            except (TypeError, ValueError):
                continue
    return out


def real_series_for(pack_dir: Path, test: ValidationTest, dates: list[str]) -> dict[str, float]:
    """La serie real con la que se compara la trayectoria del modelo, ya
    alineada a los meses de la corrida. Vacia si no hay dato para el
    periodo (V1: no hay IPC MENSUAL descargado antes de 1997-02, asi que se
    usa la variacion anual del Banco Mundial convertida a mensual
    equivalente `(1+a)^(1/12)-1` -- un proxy DERIVADO, declarado como tal,
    no una serie mensual medida)."""
    if test.real_series == "reserves_monthly":
        table = dict(_load_history_csv(pack_dir, "reserves_monthly"))
        return {d: table[d] for d in dates if d in table}
    annual = {d[:4]: v for d, v in _load_history_csv(pack_dir, "inflation_cpi_annual_linked")}
    if test.real_series == "inflation_annual":
        return {d: annual[d[:4]] for d in dates if d[:4] in annual}
    if test.real_series == "inflation_monthly_implied":
        return {
            d: ((1.0 + annual[d[:4]] / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
            for d in dates
            if d[:4] in annual
        }
    return {}


def model_series_for(test: ValidationTest, run: SeedRun) -> list[float]:
    if test.real_series == "reserves_monthly":
        return run.reserves
    if test.real_series == "inflation_annual":
        return [annualized_inflation(x) for x in run.inflation_monthly]
    return run.inflation_monthly


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------


@dataclass
class ValidationResult:
    test_id: str
    months: int
    plan: ForcedShockPlan
    runs_by_arm: dict[str, list[SeedRun]]
    metrics_by_arm: dict[str, dict]
    real: dict[str, float]
    wall_seconds: float
    diagnostics: dict = field(default_factory=dict)


def macro_price_mechanism(calibration_run_id: str) -> dict | None:
    """A5 (ADR 012 secc. 6): coeficientes de precios de la capa MACRO (ADR
    012 secc. 2: `rho_eff = rho_pi + rho_slope·clamp(...)`, distinto de la
    vieja `rho_pi + c_e` de `inflation_persistence`) para Aurora/Argentina
    (`country.json -> macro`) y para `calibration_run_id`, si esa
    calibracion trajo el grupo `"macro"` -- `None` si no (`a3_main`, y
    entonces `_lessons_section` usa `inflation_persistence` como antes de
    A5)."""
    from republica.calibration.run import CALIBRATION_ROOT

    country_raw = json.loads(
        (country_pack_dir("argentina") / "country.json").read_text(encoding="utf-8")
    )
    aurora_macro = (country_raw.get("macro") or {}).get("coefficients", {})
    path = CALIBRATION_ROOT / calibration_run_id / "coefficients.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    cal_macro = raw.get("macro")
    if not cal_macro:
        return None
    fields = ("rho_pi", "rho_slope", "pi_hi", "c_e", "c_s", "w_adapt", "md_0", "md_pi")
    return {
        "aurora": {k: aurora_macro.get(k) for k in fields},
        "calibrated": {k: cal_macro.get(k) for k in fields},
    }


def inflation_persistence(calibration_run_id: str = "a3_main") -> dict[str, float]:
    """`rho_pi + c_e`, el coeficiente TOTAL sobre la inflacion del mes
    anterior en `world/economy.py` (§4.3 + §4.2: `de` arranca en `π_t`), leido
    de disco para Aurora y para la calibracion. > 1 seria una dinamica
    explosiva (hiperinflacion endogena posible); < 1 es una contraccion.
    Metrica de la ecuacion VIEJA (sin macro, ADR 011) -- se sigue calculando
    igual para no romper reportes anteriores a A5, pero cuando la
    calibracion trae macro (ver `macro_price_mechanism`) el mecanismo
    operativo real es `rho_eff` (ADR 012 secc. 2), no esto."""
    from republica.calibration.run import CALIBRATION_ROOT
    from republica.world.config import DEFAULT_DATA_DIR

    aurora = json.loads((DEFAULT_DATA_DIR / "country.json").read_text(encoding="utf-8"))[
        "coefficients"
    ]
    out = {"aurora_rho_pi": aurora["rho_pi"], "aurora_c_e": aurora["c_e"]}
    out["aurora_total"] = out["aurora_rho_pi"] + out["aurora_c_e"]
    path = CALIBRATION_ROOT / calibration_run_id / "coefficients.json"
    if path.exists():
        cal = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
        out["calibrated_rho_pi"] = cal["rho_pi"]
        out["calibrated_c_e"] = cal["c_e"]
        out["calibrated_total"] = cal["rho_pi"] + cal["c_e"]
    return out


def fx_regime_inertness_check(
    test: ValidationTest,
    pack: CountryPack,
    plan: ForcedShockPlan,
    months: int,
    calibration_run_id: str,
    seeds: int = 3,
) -> dict:
    """Comprueba EMPIRICAMENTE si `--fx-regime <test.fx_regime>` cambia algo:
    corre las mismas semillas con el regimen pedido y con `float` y compara
    las 20 variables mes a mes. El reporte de V2 se apoya en este resultado,
    no en una lectura del codigo."""
    if not test.fx_regime:
        return {}
    from dataclasses import replace as dc_replace

    variant = dc_replace(test, fx_regime="float")
    a = run_test_arm(test, "calibrated", pack, plan, months, seeds, 1, calibration_run_id)
    b = run_test_arm(variant, "calibrated", pack, plan, months, seeds, 1, calibration_run_id)
    identical = all(
        ra.inflation_monthly == rb.inflation_monthly
        and ra.reserves == rb.reserves
        and ra.political_stability == rb.political_stability
        and ra.outcome == rb.outcome
        for ra, rb in zip(a, b, strict=True)
    )
    return {
        "compared_regimes": [test.fx_regime, "float"],
        "seeds": seeds,
        "trajectories_identical": identical,
    }


def initial_state_provenance(pack: CountryPack, start: str) -> dict:
    coverage = pack.initial_states_coverage.get(start, {})
    counts: dict[str, int] = {"source": 0, "proxy": 0, "assumed": 0}
    by_kind: dict[str, list[str]] = {"source": [], "proxy": [], "assumed": []}
    for var, kind in sorted(coverage.items()):
        counts[kind] = counts.get(kind, 0) + 1
        by_kind.setdefault(kind, []).append(var)
    return {"counts": counts, "variables": by_kind, "n_variables": len(coverage)}


def _calibration_window(calibration_run_id: str) -> dict[str, tuple[str, str]] | None:
    """`train`/`holdout` de `calibration/<calibration_run_id>/
    coefficients.json`, para declarar si una prueba de validacion cae
    IN-SAMPLE (dentro de train) o en HOLDOUT (A5, ADR 012 secc. 6: V3
    2016-2023 ahora esta dentro del train `1992-01:2023-12`, y V1 1988-1990
    dentro del holdout `1983-12:1991-12` -- se declara explicitamente en vez
    de dejarlo implicito)."""
    from republica.calibration.run import CALIBRATION_ROOT

    path = CALIBRATION_ROOT / calibration_run_id / "coefficients.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    train = raw.get("train")
    holdout = raw.get("holdout")
    if not train or not holdout:
        return None
    return {"train": (train[0], train[1]), "holdout": (holdout[0], holdout[1])}


def sample_declaration(window: dict[str, tuple[str, str]] | None, test: ValidationTest) -> str:
    """Declaracion IN-SAMPLE/HOLDOUT/fuera-de-ventana de `test` contra el
    `train`/`holdout` de la calibracion usada (A5, ADR 012 secc. 6, pedido
    explicito: "Declarar explícitamente que V3 ... ahora es in-sample ...
    y que V1 ... está en el holdout")."""
    if window is None:
        return (
            "sin ventana de train/holdout registrada (la calibracion no trae "
            "`coefficients.json` con `train`/`holdout`, o es anterior a A5)."
        )
    end = month_date(test.start, test.months)

    def within(rng: tuple[str, str]) -> bool:
        return rng[0] <= test.start and end <= rng[1]

    if within(window["train"]):
        return (
            f"IN-SAMPLE: {test.start}..{end} cae dentro del train de la calibracion "
            f"({window['train'][0]}:{window['train'][1]}) -- el modelo VIO estos datos al "
            "calibrarse; esta prueba no mide generalizacion."
        )
    if within(window["holdout"]):
        return (
            f"HOLDOUT: {test.start}..{end} cae dentro del holdout de la calibracion "
            f"({window['holdout'][0]}:{window['holdout'][1]}) -- el modelo NO vio estos datos "
            "al calibrarse (se corre una sola vez, PLAN_ARGENTINA.md #0.3/#4)."
        )
    return (
        f"NI IN-SAMPLE NI HOLDOUT: {test.start}..{end} cae fuera de train "
        f"({window['train'][0]}:{window['train'][1]}) y de holdout "
        f"({window['holdout'][0]}:{window['holdout'][1]}) de la calibracion."
    )


def _v4_block_reason(pack: CountryPack) -> str | None:
    """`None` si el paquete trae una epoca de partidos argentinos que cubre
    `V4.start` (ADR 013, en curso en paralelo) -- si no, la razon por la
    que V4 se salta (A5, ADR 012 secc. 6: "dejá la definición de V4 lista
    ... detrás de una condición para que validate la salte con aviso si el
    pack no trae época de partidos")."""
    if pack.era is not None and pack.era.parties is not None:
        return None
    return (
        "el paquete de Argentina todavía no trae una época de partidos (ADR 013, en curso "
        f"en paralelo) que cubra {TESTS_BY_ID['V4'].start} -- se corre cuando ADR 013 esté "
        "integrado."
    )


def build_registration(
    tests: list[ValidationTest],
    months_cap: int | None,
    calibration_run_id: str,
    seeds: int,
    v4_block_reasons: dict[str, str] | None = None,
    regime_transitions: bool = False,
) -> dict:
    """El registro que se escribe ANTES de correr nada (hipotesis, shocks
    forzados pedidos vs. efectivamente aplicables, procedencia del estado
    inicial). Ver docstring del modulo. `v4_block_reasons` (A5, ADR 012
    secc. 6): `{test_id: razon}` de las pruebas que se registran pero NO se
    corren (hoy solo puede pasar con `V4`) -- se documenta igual la
    hipotesis/shocks pedidos (protocolo de honestidad: la definicion queda
    fijada ANTES de saber si se puede correr), marcando `"skipped"`."""
    v4_block_reasons = v4_block_reasons or {}
    pack_dir = country_pack_dir("argentina")
    window = _calibration_window(calibration_run_id)
    entries = []
    for test in tests:
        months = min(test.months, months_cap) if months_cap else test.months
        plan = resolve_forced_shocks(pack_dir, test, months)
        skip_reason = v4_block_reasons.get(test.test_id)
        entry = {
            "test_id": test.test_id,
            "title": test.title,
            "hypothesis": HYPOTHESES[test.test_id],
            "metric": METRICS[test.test_id],
            "adr_forced_shocks": ADR_FORCED_SHOCKS[test.test_id],
            "start": test.start,
            "months": months,
            "months_adr": test.months,
            "fx_regime": test.fx_regime,
            "forced_shocks_requested": plan.requested,
            "forced_shocks_applied": {str(k): v for k, v in sorted(plan.forced.items())},
            "forced_shocks_excluded_endogenous": plan.excluded_endogenous,
            "sample_declaration": sample_declaration(window, test),
            "random_shocks_enabled": True,
            "skipped": skip_reason is not None,
        }
        if skip_reason is not None:
            entry["skipped_reason"] = skip_reason
        else:
            pack = _load_pack(test, months, regime_transitions)
            entry["initial_state_provenance"] = initial_state_provenance(pack, test.start)
        entries.append(entry)
    return {
        "adr": "ADR 011 secc. 8 (A4) / ADR 012 secc. 6 (A5, V4)",
        "registered_before_running": True,
        "country": "argentina",
        "calibration_run_id": calibration_run_id,
        "seeds": seeds,
        "months_cap": months_cap,
        # ADR 015: queda REGISTRADO antes de correr si el modelo de riesgo
        # endogeno del regimen estuvo prendido (cambia que puede pasar con
        # `regime_mode` en las tres pruebas).
        "regime_endogenous_transitions": regime_transitions,
        "arms": list(ARMS),
        "control_hypothesis": HYPOTHESES["C"],
        "control_metric": METRICS["C"],
        "honesty_sentence": HONESTY_SENTENCE,
        "tests": entries,
    }


def run_validation(
    out_dir: Path,
    *,
    seeds: int = 50,
    seed_base: int = 1,
    months_cap: int | None = None,
    calibration_run_id: str = "a3_main",
    test_ids: list[str] | None = None,
    resamples: int = 2000,
    make_plots: bool = True,
    regime_transitions: bool = False,
    progress=None,
) -> dict:
    """Corre A4/A5 completo y escribe `registration.json`, `results.json`,
    `report.md` y `plots/` en `out_dir`. `test_ids=None` corre
    `DEFAULT_TEST_IDS` (V1-V3, NO V4 -- ver `TESTS`); pedir `V4`
    explícitamente (`test_ids=["V4"]` o `--tests V1,V2,V3,V4`) la intenta
    igual y la salta con aviso (`_v4_block_reason`) si el paquete no trae
    partidos por época todavía (ADR 013, en curso en paralelo)."""
    requested = [TESTS_BY_ID[t] for t in (test_ids or list(DEFAULT_TEST_IDS))]
    out_dir.mkdir(parents=True, exist_ok=True)

    pack_dir = country_pack_dir("argentina")
    v4_block_reasons: dict[str, str] = {}
    tests: list[ValidationTest] = []
    for test in requested:
        if test.test_id == "V4":
            months = min(test.months, months_cap) if months_cap else test.months
            v4_pack = _load_pack(test, months, regime_transitions)
            reason = _v4_block_reason(v4_pack)
            if reason is not None:
                v4_block_reasons["V4"] = reason
                if progress:
                    progress(f"V4 SALTADA: {reason}")
                continue
        tests.append(test)

    registration = build_registration(
        requested,
        months_cap,
        calibration_run_id,
        seeds,
        v4_block_reasons,
        regime_transitions=regime_transitions,
    )
    (out_dir / "registration.json").write_text(
        json.dumps(registration, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    results: list[ValidationResult] = []
    t_start = time.perf_counter()
    for test in tests:
        months = min(test.months, months_cap) if months_cap else test.months
        plan = resolve_forced_shocks(pack_dir, test, months)
        pack = _load_pack(test, months, regime_transitions)
        t0 = time.perf_counter()
        runs_by_arm: dict[str, list[SeedRun]] = {}
        for arm in ARMS:
            if progress:
                progress(f"{test.test_id} ({ARM_LABELS[arm]}) x{seeds} semillas")
            runs_by_arm[arm] = run_test_arm(
                test, arm, pack, plan, months, seeds, seed_base, calibration_run_id
            )
        all_dates = [month_date(test.start, i) for i in range(1, months + 1)]
        real = real_series_for(pack_dir, test, all_dates)
        metrics_by_arm = {}
        for arm, runs in runs_by_arm.items():
            if test.test_id == "V1":
                metrics_by_arm[arm] = metrics_v1(runs, months, resamples)
            elif test.test_id == "V2":
                metrics_by_arm[arm] = metrics_v2(runs, months, resamples, real)
            elif test.test_id == "V4":
                metrics_by_arm[arm] = metrics_v4(runs, months, resamples)
            else:
                metrics_by_arm[arm] = metrics_v3(runs, months, resamples)
        diagnostics: dict = {}
        if test.fx_regime:
            if progress:
                progress(f"{test.test_id} (diagnóstico) fx-regime {test.fx_regime} vs float")
            diagnostics["fx_regime_inertness"] = fx_regime_inertness_check(
                test, pack, plan, months, calibration_run_id, seeds=min(3, seeds)
            )
        results.append(
            ValidationResult(
                test_id=test.test_id,
                months=months,
                plan=plan,
                runs_by_arm=runs_by_arm,
                metrics_by_arm=metrics_by_arm,
                real=real,
                wall_seconds=time.perf_counter() - t0,
                diagnostics=diagnostics,
            )
        )
    wall = time.perf_counter() - t_start

    plots: dict[str, str] = {}
    if make_plots:
        plots = write_plots(out_dir, results)

    payload = {
        "registration": registration,
        "wall_seconds": wall,
        "tests": [
            {
                "test_id": r.test_id,
                "months": r.months,
                "wall_seconds": r.wall_seconds,
                "metrics": r.metrics_by_arm,
                "diagnostics": r.diagnostics,
                "random_shocks_observed": {
                    arm: sorted({s for run in runs for s in run.random_shocks})
                    for arm, runs in r.runs_by_arm.items()
                },
            }
            for r in results
        ],
        "control_verdict": control_verdict(results),
        "inflation_persistence": inflation_persistence(calibration_run_id),
        "v4_skipped_reasons": v4_block_reasons,
        "honesty_sentence": HONESTY_SENTENCE,
    }
    (out_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_report(out_dir, registration, results, wall, plots, calibration_run_id, seeds)
    return payload


def control_verdict(results: list[ValidationResult]) -> dict:
    """Fila C del ADR: "Aurora sin calibrar falla al menos una de las tres"."""
    failed = [r.test_id for r in results if not r.metrics_by_arm["aurora"]["passes"]]
    passed_calibrated = [r.test_id for r in results if r.metrics_by_arm["calibrated"]["passes"]]
    return {
        "aurora_failed_tests": failed,
        "calibrated_passed_tests": passed_calibrated,
        "passes": len(failed) >= 1,
    }


# --------------------------------------------------------------------------
# Graficos
# --------------------------------------------------------------------------


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, len(sorted_values) - 1)
    frac = pos - lo_i
    return sorted_values[lo_i] * (1.0 - frac) + sorted_values[hi_i] * frac


def _quantile_bands(series: list[list[float]], months: int) -> tuple[list, list, list]:
    """Mediana e IQR mes a mes sobre las semillas VIVAS en ese mes (las
    corridas que terminaron antes -- `collapse`/`hyperinflation` -- dejan de
    contribuir: no se rellenan con su ultimo valor, que inventaria una
    trayectoria que el motor nunca simulo)."""
    med: list[float | None] = []
    lo: list[float | None] = []
    hi: list[float | None] = []
    for i in range(months):
        vals = sorted(s[i] for s in series if i < len(s))
        if not vals:
            med.append(None)
            lo.append(None)
            hi.append(None)
            continue
        med.append(_percentile(vals, 0.5))
        lo.append(_percentile(vals, 0.25))
        hi.append(_percentile(vals, 0.75))
    return med, lo, hi


def write_plots(out_dir: Path, results: list[ValidationResult]) -> dict[str, str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - extra `analysis` no instalado
        return {}

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}
    for res in results:
        test = TESTS_BY_ID[res.test_id]
        fig, ax = plt.subplots(figsize=(9, 5.2))
        x = list(range(1, res.months + 1))
        colors = {"calibrated": "#1f77b4", "aurora": "#ff7f0e"}
        for arm, runs in res.runs_by_arm.items():
            series = [model_series_for(test, r) for r in runs]
            med, lo, hi = _quantile_bands(series, res.months)
            xs = [xi for xi, m in zip(x, med, strict=False) if m is not None]
            ms = [m for m in med if m is not None]
            los = [v for v in lo if v is not None]
            his = [v for v in hi if v is not None]
            ax.plot(xs, ms, label=f"modelo {ARM_LABELS[arm]} (mediana)", color=colors[arm], lw=2)
            ax.fill_between(
                xs,
                los,
                his,
                alpha=0.18,
                color=colors[arm],
                label=f"IQR {ARM_LABELS[arm]} (semillas vivas)",
            )
        if res.real:
            dates = [month_date(test.start, i) for i in range(1, res.months + 1)]
            rx = [i + 1 for i, d in enumerate(dates) if d in res.real]
            ry = [res.real[d] for d in dates if d in res.real]
            ax.plot(rx, ry, color="black", ls="--", lw=2, label=f"real: {test.real_series_label}")
        ax.set_xlabel(f"mes de la corrida (1 = {test.start})")
        ax.set_ylabel(test.y_label)
        ax.set_title(f"{test.test_id} — {test.start} + {res.months} meses")
        if res.test_id in ("V1", "V3"):
            ax.set_yscale("symlog", linthresh=1)
        ax.grid(alpha=0.25)
        # Leyenda DEBAJO del eje: con escalas log y series que se cruzan,
        # cualquier `loc` de adentro tapaba una de las trayectorias.
        ax.legend(
            fontsize=7,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.16),
            ncol=3,
            frameon=False,
        )
        fig.tight_layout()
        name = f"{res.test_id.lower()}.png"
        fig.savefig(plots_dir / name, dpi=120)
        plt.close(fig)
        made[res.test_id] = f"plots/{name}"
    return made


# --------------------------------------------------------------------------
# Reporte
# --------------------------------------------------------------------------


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "sin dato"
    return f"{value:,.{digits}f}{suffix}".replace(",", " ")


def _fmt_ci(ci, digits: int = 2, suffix: str = "") -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return "sin dato"
    return f"[{_fmt(lo, digits, suffix)}, {_fmt(hi, digits, suffix)}]"


def _fmt_pct(fraction, digits: int = 1) -> str:
    return "sin dato" if fraction is None else f"{fraction * 100:.{digits}f} %"


def _fmt_pct_ci(ci, digits: int = 1) -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return "sin dato"
    return f"[{_fmt_pct(lo, digits)}, {_fmt_pct(hi, digits)}]"


def _verdict_plain(passes: bool) -> str:
    return "CUMPLIDA" if passes else "NO CUMPLIDA"


def _verdict(passes: bool) -> str:
    return f"**{_verdict_plain(passes)}**"


def _forced_shocks_block(entry: dict) -> list[str]:
    lines: list[str] = []
    lines.append(f"- Shocks forzados que pide el ADR: *{entry['adr_forced_shocks']}*.")
    if not entry["forced_shocks_requested"]:
        lines.append(
            "- Shocks forzados efectivamente aplicados: **ninguno** (el ADR no pide forzar "
            "ninguno en esta prueba)."
        )
    else:
        for req in entry["forced_shocks_requested"]:
            if req["matched"]:
                rows = "; ".join(
                    f"`{m['shock_id']}` {m['date']} (mes {m['month_index']}, "
                    f"duración {m['duration_months']} meses — {m['title']})"
                    for m in req["matched"]
                )
                lines.append(f"- `{req['label']}` → {rows}")
            else:
                lines.append(
                    f"- `{req['label']}` → **NO APLICADO**: `politics/shocks_calendar.csv` no "
                    f"tiene ninguna fila `{req['shock_id']}` en la ventana "
                    f"`{req['window']}`. No se inventa la fila "
                    "(PLAN_ARGENTINA.md §0.1); queda registrado como faltante."
                )
        applied = entry["forced_shocks_applied"]
        lines.append(
            f"- `forced_shocks` pasado al motor: `{applied if applied else '{}'}` "
            "(índice de mes → shock)."
        )
    lines.append(
        "- Además siguen activos los shocks **aleatorios** de `shocks.json` "
        "(`shocks_enabled=True`, igual que en cualquier `republica run`): la lista de forzados "
        "no es la lista de shocks que ocurrieron."
    )
    return lines


def _provenance_block(entry: dict) -> list[str]:
    prov = entry["initial_state_provenance"]
    counts = prov["counts"]
    lines = [
        f"- Estado inicial `{entry['start']}` ({prov['n_variables']} variables): "
        f"**{counts.get('source', 0)} `source`**, **{counts.get('proxy', 0)} `proxy`**, "
        f"**{counts.get('assumed', 0)} `assumed`**.",
    ]
    for kind in ("source", "proxy", "assumed"):
        names = prov["variables"].get(kind) or []
        if names:
            lines.append(f"  - `{kind}`: {', '.join(f'`{n}`' for n in names)}")
    return lines


def _comparison_table(results: list[ValidationResult], calibration_run_id: str) -> list[str]:
    lines = [
        f"| prueba | métrica principal | calibrado (`{calibration_run_id}`) | "
        "Aurora sin calibrar | veredicto calibrado | veredicto Aurora |",
        "|---|---|---|---|---|---|",
    ]
    for res in results:
        cal = res.metrics_by_arm["calibrated"]
        aur = res.metrics_by_arm["aurora"]
        if res.test_id == "V1":
            label = "fracción de semillas en `hyperinflation`"
            cv = (
                f"{_fmt_pct(cal['hyperinflation_fraction'])} "
                f"IC95 {_fmt_pct_ci(cal['hyperinflation_fraction_ci'])}"
            )
            av = (
                f"{_fmt_pct(aur['hyperinflation_fraction'])} "
                f"IC95 {_fmt_pct_ci(aur['hyperinflation_fraction_ci'])}"
            )
        elif res.test_id == "V2":
            label = "fracción con `sovereign_default`/`collapse` en meses 36–54"
            cv = (
                f"{_fmt_pct(cal['default_or_collapse_fraction'])} "
                f"IC95 {_fmt_pct_ci(cal['default_or_collapse_fraction_ci'])}"
            )
            av = (
                f"{_fmt_pct(aur['default_or_collapse_fraction'])} "
                f"IC95 {_fmt_pct_ci(aur['default_or_collapse_fraction_ci'])}"
            )
        elif res.test_id == "V4":
            label = "inflación final (umbral 100 %) y derrota electoral (umbral 70 %)"
            cv = (
                f"infl {_fmt(cal['inflation_annual_final_median'], 1, ' %')}, derrota "
                f"{_fmt_pct(cal['election_defeat_fraction'])} "
                f"IC95 {_fmt_pct_ci(cal['election_defeat_fraction_ci'])}"
            )
            av = (
                f"infl {_fmt(aur['inflation_annual_final_median'], 1, ' %')}, derrota "
                f"{_fmt_pct(aur['election_defeat_fraction'])} "
                f"IC95 {_fmt_pct_ci(aur['election_defeat_fraction_ci'])}"
            )
        else:
            label = "mediana de la inflación anualizada final (umbral 80 %)"
            cv = (
                f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} "
                f"IC95 {_fmt_ci(cal['inflation_annual_final_ci'], 1, ' %')}"
            )
            av = (
                f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} "
                f"IC95 {_fmt_ci(aur['inflation_annual_final_ci'], 1, ' %')}"
            )
        lines.append(
            f"| {res.test_id} | {label} | {cv} | {av} | "
            f"{_verdict(cal['passes'])} | {_verdict(aur['passes'])} |"
        )
    return lines


def _test_section(res: ValidationResult, entry: dict, plot: str | None) -> list[str]:
    test = TESTS_BY_ID[res.test_id]
    cal = res.metrics_by_arm["calibrated"]
    aur = res.metrics_by_arm["aurora"]
    adr_ref = "ADR 011 §8" if test.test_id != "V4" else "A5, ADR 012 secc. 6"
    lines = [
        f"## {test.title}",
        "",
        f"**Hipótesis registrada antes de correr ({adr_ref}, literal):** *{entry['hypothesis']}*",
        "",
        f"**Métrica ({adr_ref}, literal):** *{entry['metric']}*",
        "",
        f"Corrida: `--country argentina --start {test.start}` × "
        f"{entry['months']} meses × {len(res.runs_by_arm['calibrated'])} semillas por brazo"
        + (f", `--fx-regime {test.fx_regime}`" if test.fx_regime else "")
        + ", `--historical-exogenous`, `--regime-mode auto`, política `passive`.",
        "",
        "### Shocks forzados",
        "",
    ]
    lines += _forced_shocks_block(entry)
    lines += ["", "### Procedencia del estado inicial", ""]
    lines += _provenance_block(entry)
    lines += ["", "### Resultado", ""]

    if res.test_id == "V1":
        lines += [
            "| brazo | fracción en `hyperinflation` | IC95 (bootstrap sobre semillas) | "
            "mes mediano | inflación mensual final (mediana) | outcomes |",
            "|---|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt_pct(m['hyperinflation_fraction'])} | "
                f"{_fmt_pct_ci(m['hyperinflation_fraction_ci'])} | "
                f"{_fmt(m['hyperinflation_median_month'], 1)} | "
                f"{_fmt(m['inflation_monthly_final_median'], 2, ' %')} | "
                f"{m['outcomes']} |"
            )
    elif res.test_id == "V2":
        lines += [
            "| brazo | fracción `sovereign_default`/`collapse` en meses "
            + (
                "36–54 (ventana VACÍA con `--months-cap`)"
                if cal.get("window_empty")
                else f"{cal['window_months'][0]}–{cal['window_months'][1]}"
            )
            + " | IC95 | RMSE reservas vs real (USD M, mediana) | IC95 | outcomes |",
            "|---|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt_pct(m['default_or_collapse_fraction'])} | "
                f"{_fmt_pct_ci(m['default_or_collapse_fraction_ci'])} | "
                f"{_fmt(m['reserves_rmse_median'], 0)} | "
                f"{_fmt_ci(m['reserves_rmse_ci'], 0)} | {m['outcomes']} |"
            )
        lines += [
            "",
            "Baseline ingenuo de reservas (persistencia: reservas reales congeladas en el nivel "
            f"real de {test.start}): RMSE {_fmt(cal['reserves_rmse_persistence'], 0)} USD M.",
        ]
    elif res.test_id == "V4":
        lines += [
            "| brazo | inflación anualizada final (mediana) | IC95 | derrota electoral "
            "(cualquier elección de la ventana) | IC95 | meses simulados (mediana) | outcomes |",
            "|---|---|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt(m['inflation_annual_final_median'], 1, ' %')} | "
                f"{_fmt_ci(m['inflation_annual_final_ci'], 1, ' %')} | "
                f"{_fmt_pct(m['election_defeat_fraction'])} | "
                f"{_fmt_pct_ci(m['election_defeat_fraction_ci'])} | "
                f"{_fmt(m['median_months_run'], 0)} | {m['outcomes']} |"
            )
        n_cal_total = sum(cal["outcomes"].values())
        n_cal_collapse = cal["outcomes"].get("collapse", 0) + cal["outcomes"].get(
            "hyperinflation", 0
        )
        lines += [
            "",
            f"Semillas calibradas que terminan antes de los {entry['months']} meses "
            f"(`collapse`/`hyperinflation`, la elección de fin de mandato puede no llegar a "
            f"celebrarse): {n_cal_collapse} de {n_cal_total}. Si esa fracción es alta, la "
            "hipótesis electoral de V4 no se puede evaluar con la misma confianza que la de "
            "inflación: en esas semillas la corrida termina antes de que se celebre la elección "
            "de fin de mandato.",
        ]
    else:
        lines += [
            "| brazo | inflación anualizada final (mediana) | IC95 | meses simulados (mediana) "
            "| outcomes |",
            "|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt(m['inflation_annual_final_median'], 1, ' %')} | "
                f"{_fmt_ci(m['inflation_annual_final_ci'], 1, ' %')} | "
                f"{_fmt(m['median_months_run'], 0)} | {m['outcomes']} |"
            )
        lines += [
            "",
            "| elección | resultado real | brazo | semillas en que la elección ocurrió | "
            "aciertos | IC95 |",
            "|---|---|---|---|---|---|",
        ]
        for date in V3_REAL_ELECTIONS:
            for arm, m in (("calibrated", cal), ("aurora", aur)):
                e = m["elections"][date]
                lines.append(
                    f"| {date} | oficialismo derrotado | {ARM_LABELS[arm]} | "
                    f"{e['n_held']} | {_fmt_pct(e['hit_fraction'])} | "
                    f"{_fmt_pct_ci(e['hit_fraction_ci'])} |"
                )

    lines += [
        "",
        f"**Veredicto (calibrado): {_verdict_plain(cal['passes'])}.** "
        f"**Veredicto (Aurora sin calibrar): {_verdict_plain(aur['passes'])}.**",
        "",
    ]
    if plot:
        lines += [
            f"![{res.test_id}]({plot})",
            "",
            "*Trayectoria mediana con banda intercuartil por brazo contra "
            f"{test.real_series_label}. "
            "La banda se calcula solo sobre las semillas VIVAS en cada mes: una corrida terminada "
            "por `collapse`/`hyperinflation` deja de contribuir en vez de repetir su "
            "último valor.*",
            "",
        ]
    return lines


def _v2_rmse_note(results: list[ValidationResult]) -> str:
    v2 = next((r for r in results if r.test_id == "V2"), None)
    if not v2:
        return "sin dato"
    c = v2.metrics_by_arm["calibrated"]
    a = v2.metrics_by_arm["aurora"]
    cal, aur, base = (
        c["reserves_rmse_median"],
        a["reserves_rmse_median"],
        c["reserves_rmse_persistence"],
    )
    if cal is None or aur is None or not base:
        return "sin dato"
    return (
        f"{(1 - cal / aur) * 100:.1f} % respecto de Aurora y {(1 - cal / base) * 100:.1f} % "
        "respecto del baseline ingenuo de persistencia"
    )


def _v2_reserves_range(v2: ValidationResult) -> str:
    runs = v2.runs_by_arm["calibrated"]
    first = statistics.median([r.reserves[0] for r in runs])
    last = statistics.median([r.reserves[-1] for r in runs])
    return f"mediana {first:,.0f} → {last:,.0f} USD M".replace(",", " ")


def _v3_election_note(results: list[ValidationResult]) -> str:
    v3 = next((r for r in results if r.test_id == "V3"), None)
    if not v3:
        return "sin dato"
    c = v3.metrics_by_arm["calibrated"]["elections"]["2019-12"]["hit_fraction"]
    a = v3.metrics_by_arm["aurora"]["elections"]["2019-12"]["hit_fraction"]
    return (
        f"el acierto de la elección de 2019 pasa de {_fmt_pct(a)} a {_fmt_pct(c)} de las semillas"
    )


def _v3_collapse_note(results: list[ValidationResult]) -> str:
    v3 = next((r for r in results if r.test_id == "V3"), None)
    if not v3:
        return "sin dato"
    m = v3.metrics_by_arm["calibrated"]
    total = sum(m["outcomes"].values())
    n = m["outcomes"].get("collapse", 0)
    return (
        f"{n} de {total} semillas calibradas de V3 terminan en `collapse` antes del mes "
        f"{v3.months} y la elección de 2023 se celebra en "
        f"{m['elections']['2023-12']['n_held']} de {total}"
    )


def _value_of_calibration_table(results: list[ValidationResult]) -> list[str]:
    """Fila C del ADR 011 secc. 8: "la diferencia con el calibrado es el
    'valor' de la calibracion". Se compara metrica por metrica contra el
    dato historico (columna `real`), porque ningun brazo cumple ninguna
    hipotesis y comparar veredictos no distinguiria nada."""
    by_id = {r.test_id: r for r in results}
    rows: list[tuple[str, str, float | None, float | None, float | None, bool]] = []
    v1 = by_id.get("V1")
    if v1:
        c, a = v1.metrics_by_arm["calibrated"], v1.metrics_by_arm["aurora"]
        rows.append(
            (
                "V1",
                "fracción de semillas en `hyperinflation` (%)",
                100.0,
                c["hyperinflation_fraction"] * 100.0,
                a["hyperinflation_fraction"] * 100.0,
                False,
            )
        )
        rows.append(
            (
                "V1",
                "inflación mensual al mes 24 (%) — real jul-1989 ≈ 33 %/mes",
                33.0,
                c["inflation_monthly_final_median"],
                a["inflation_monthly_final_median"],
                False,
            )
        )
    v2 = by_id.get("V2")
    if v2:
        c, a = v2.metrics_by_arm["calibrated"], v2.metrics_by_arm["aurora"]
        rows.append(
            (
                "V2",
                "fracción con `sovereign_default`/`collapse` en meses 36–54 (%)",
                100.0,
                c["default_or_collapse_fraction"] * 100.0,
                a["default_or_collapse_fraction"] * 100.0,
                False,
            )
        )
        rows.append(
            (
                "V2",
                "RMSE de reservas vs real (USD M; baseline persistencia "
                f"{_fmt(c['reserves_rmse_persistence'], 0)})",
                0.0,
                c["reserves_rmse_median"],
                a["reserves_rmse_median"],
                False,
            )
        )
    v3 = by_id.get("V3")
    if v3:
        c, a = v3.metrics_by_arm["calibrated"], v3.metrics_by_arm["aurora"]
        rows.append(
            (
                "V3",
                "inflación anualizada final (%) — real 2023: 135 % (BM)",
                135.0,
                c["inflation_annual_final_median"],
                a["inflation_annual_final_median"],
                False,
            )
        )
        for date in V3_REAL_ELECTIONS:
            rows.append(
                (
                    "V3",
                    f"acierto electoral {date} (oficialismo derrotado, % de semillas)",
                    100.0,
                    c["elections"][date]["hit_fraction"] * 100.0,
                    a["elections"][date]["hit_fraction"] * 100.0,
                    True,
                )
            )

        def _survival(m: dict) -> float:
            total = max(1, sum(m["outcomes"].values()))
            return 100.0 * (1.0 - m["outcomes"].get("collapse", 0) / total)

        rows.append(
            (
                "V3",
                "semillas que llegan al mes 96 sin `collapse` (%)",
                100.0,
                _survival(c),
                _survival(a),
                False,
            )
        )

    lines = [
        "| prueba | métrica | real | calibrado (`a3_main`) | Aurora sin calibrar | más cerca "
        "de la historia |",
        "|---|---|---|---|---|---|",
    ]
    for test_id, label, real, cal, aur, _is_pct in rows:
        if cal is None or aur is None or real is None:
            winner = "sin dato"
        elif abs(cal - real) < abs(aur - real):
            winner = "**calibrado**"
        elif abs(aur - real) < abs(cal - real):
            winner = "**Aurora**"
        else:
            winner = "empate"
        lines.append(
            f"| {test_id} | {label} | {_fmt(real, 1)} | {_fmt(cal, 1)} | {_fmt(aur, 1)} | "
            f"{winner} |"
        )
    return lines


def write_report(
    out_dir: Path,
    registration: dict,
    results: list[ValidationResult],
    wall_seconds: float,
    plots: dict[str, str],
    calibration_run_id: str,
    seeds: int,
) -> Path:
    entries = {e["test_id"]: e for e in registration["tests"]}
    control = control_verdict(results)
    window = _calibration_window(calibration_run_id)
    window_note = (
        f"train `{window['train'][0]}:{window['train'][1]}`, holdout "
        f"`{window['holdout'][0]}:{window['holdout'][1]}`"
        if window
        else "ventana de train/holdout no registrada en `coefficients.json`"
    )
    has_macro = macro_price_mechanism(calibration_run_id) is not None
    adr_label = "ADR 012 secc. 6 (A5)" if has_macro else "ADR 011 §8 (A4)"
    lines: list[str] = [
        f"# Validación histórica de Argentina — {adr_label}",
        "",
        f"País: `argentina`. Calibración: `{calibration_run_id}` ({window_note}). "
        f"Macro (ADR 012): {'activo' if has_macro else 'inactivo (bloque bimonetario viejo)'}. "
        "Brazos: calibrado y **Aurora sin calibrar** (fila C del ADR).",
        f"Semillas por prueba y brazo: **{seeds}**. Tiempo de pared total: "
        f"**{wall_seconds:.1f} s** "
        f"({', '.join(f'{r.test_id} {r.wall_seconds:.1f} s' for r in results)}).",
        "",
        "Las hipótesis, los shocks forzados y la procedencia del estado inicial se registraron "
        "en `registration.json` **antes** de correr la primera simulación; este reporte solo "
        "las lee. Métricas crudas por prueba y brazo: `results.json`.",
        "",
    ]
    skipped = [e for e in registration["tests"] if e.get("skipped")]
    if skipped:
        lines += [
            "## Pruebas registradas pero NO corridas en este reporte",
            "",
        ]
        for e in skipped:
            lines.append(
                f"- **{e['test_id']}** ({e['title']}). Hipótesis registrada (no evaluada aún): "
                f"*{e['hypothesis']}*. Motivo: {e['skipped_reason']}"
            )
        lines += [""]
    lines += [
        f"## Resumen: los {len(results)} veredicto{'s' if len(results) != 1 else ''}",
        "",
    ]
    lines += _comparison_table(results, calibration_run_id)
    lines += [
        "",
        f"**C Control.** Hipótesis registrada (ADR 011 §8, literal): *{HYPOTHESES['C']}*. "
        f"Métrica: *{METRICS['C']}*. Aurora sin calibrar falla "
        f"{len(control['aurora_failed_tests'])} de {len(results)} pruebas "
        f"({', '.join(control['aurora_failed_tests']) or 'ninguna'}): "
        f"{_verdict(control['passes'])}.",
        "",
        '### El "valor" de la calibración (fila C del ADR)',
        "",
        "La columna «real» es el dato histórico correspondiente y la última marca el brazo más "
        "cercano a ese dato métrica por métrica (independiente del veredicto binario de arriba).",
        "",
    ]
    lines += _value_of_calibration_table(results)
    lines += [
        "",
        f"Notas puntuales: RMSE de reservas (V2) calibrado vs Aurora/persistencia: "
        f"{_v2_rmse_note(results)}. Acierto electoral 2019 (V3): {_v3_election_note(results)}. "
        f"Supervivencia (V3): {_v3_collapse_note(results)}. Ver la sección «Qué aprendimos del "
        "modelo» más abajo para la lectura mecánica completa.",
        "",
    ]
    for res in results:
        lines += _test_section(res, entries[res.test_id], plots.get(res.test_id))

    lines += _lessons_section(results, calibration_run_id)
    lines += _cannot_conclude_section(results, calibration_run_id)
    lines += [
        "## Limitaciones",
        "",
        f"> {HONESTY_SENTENCE}",
        "",
    ]
    text = "\n".join(lines)
    path = out_dir / "report.md"
    path.write_text(text, encoding="utf-8")
    return path


def _lessons_section(results: list[ValidationResult], calibration_run_id: str) -> list[str]:
    """Dispatcher A5 (ADR 012 secc. 6): `_lessons_section_macro` cuando
    `calibration_run_id` trae el grupo `"macro"` (a5_macro y sucesores),
    `_lessons_section_legacy` (la narrativa ORIGINAL de A4, ADR 011, sin
    tocar) cuando no (`a3_main` -- las afirmaciones de esa narrativa,
    p.ej. "`--fx-regime peg` es inerte", son ESPECIFICAS del motor sin ADR
    012 y dejan de ser ciertas con macro activo, asi que NO se reusan para
    una calibracion que si lo trae)."""
    if macro_price_mechanism(calibration_run_id) is not None:
        return _lessons_section_macro(results, calibration_run_id)
    return _lessons_section_legacy(results)


def _lessons_section_macro(results: list[ValidationResult], calibration_run_id: str) -> list[str]:
    """Explicacion MECANICA para una calibracion CON macro (A5, ADR 012
    secc. 6): a diferencia de `_lessons_section_legacy` (ADR 011, donde
    `--fx-regime peg` no hacia nada y las reservas no tenian balance de
    pagos), aca `step_macro_economy` gobierna precios/regimen cambiario/
    balance de pagos de verdad -- la narrativa describe ESE mecanismo, con
    los valores REALES de esta corrida (no reusa ningun numero de A3/A4)."""
    by_id = {r.test_id: r for r in results}
    mech = macro_price_mechanism(calibration_run_id) or {}
    aurora_m = mech.get("aurora", {})
    cal_m = mech.get("calibrated", {})

    def mv(d: dict, k: str) -> str:
        v = d.get(k)
        return "sin dato" if v is None else f"{v:.4g}"

    lines = ["## Qué aprendimos del modelo (A5, ADR 012)", "", "### V1 — hiperinflación", ""]
    v1 = by_id.get("V1")
    if v1:
        cal = v1.metrics_by_arm["calibrated"]
        aur = v1.metrics_by_arm["aurora"]
        lines += [
            "Con macro activo (ADR 012 secc. 2) la persistencia efectiva de la inflación es "
            "`rho_eff = rho_pi + rho_slope·clamp((inflation_lag1 - pi_hi)/pi_hi, 0, 2)`, no la "
            "`rho_pi + c_e` fija de la ecuación vieja (ADR 011): con inflación mensual alta "
            "`rho_eff` puede superar 1 (hiperinflación como régimen alcanzable, no un shock). "
            f"Valores de esta corrida (`rho_pi`/`rho_slope`/`pi_hi`/`c_s`): Aurora "
            f"`{mv(aurora_m, 'rho_pi')}`/`{mv(aurora_m, 'rho_slope')}`/`{mv(aurora_m, 'pi_hi')}`/"
            f"`{mv(aurora_m, 'c_s')}`, calibrado "
            f"`{mv(cal_m, 'rho_pi')}`/`{mv(cal_m, 'rho_slope')}`/`{mv(cal_m, 'pi_hi')}`/"
            f"`{mv(cal_m, 'c_s')}`.",
            "",
            f"Empíricamente, desde 1988-06 real ({v1.months} meses, sin shocks forzados): "
            f"{_fmt_pct(cal['hyperinflation_fraction'])} de semillas calibradas "
            f"(IC95 {_fmt_pct_ci(cal['hyperinflation_fraction_ci'])}) y "
            f"{_fmt_pct(aur['hyperinflation_fraction'])} de Aurora "
            f"(IC95 {_fmt_pct_ci(aur['hyperinflation_fraction_ci'])}) cruzan `hyperinflation`; "
            "inflación mensual mediana final: "
            f"{_fmt(cal['inflation_monthly_final_median'], 2, ' %')} "
            f"(calibrado) vs {_fmt(aur['inflation_monthly_final_median'], 2, ' %')} (Aurora), "
            "contra ~33 %/mes real de 1989 (Banco Mundial). Ver la tabla de arriba (Resumen) "
            "para el veredicto formal contra la hipótesis registrada.",
            "",
        ]
    lines += ["### V2 — régimen cambiario y balance de pagos", ""]
    v2 = by_id.get("V2")
    if v2:
        cal = v2.metrics_by_arm["calibrated"]
        inert = v2.diagnostics.get("fx_regime_inertness", {})
        verdict = (
            "idénticas estado a estado con la misma semilla (`peg` sigue sin efecto en ESTA "
            "corrida -- revisar `k_flight_peg`/`k_int` calibrados)"
            if inert.get("trajectories_identical")
            else "DISTINTAS (esperado con macro activo: `fx_regime` gobierna `de`, la "
            "intervención y `k_k` -- ADR 012 secc. 3)"
        )
        lines += [
            "Con macro activo, `fx_regime` gobierna `de` (secc. 3): `peg` fija `de=0` mientras "
            "`reserves > R_min = rm·importaciones_3m` e interviene vendiendo reservas; si "
            "`reserves < R_min` salta a `float` (`fx_regime_exit`, `shock_conf` negativo, "
            "`banking_crisis` con `exit_banking_crisis_p`). Las reservas (secc. 4) son "
            "`reserves' = reserves + current_account + capital_account - intervention_usd`, "
            "con `current_account`/`capital_account` dependientes de `commodity_price`/`rer`/"
            "`r_gap`/`dollar_demand`/`default_risk` -- ya no una caminata sin ancla. "
            f"Diagnóstico empírico (`fx_regime_inertness`, {inert.get('seeds', 0)} semillas): "
            f"`peg` vs `float` dan trayectorias {verdict}.",
            "",
            f"Reservas: RMSE mediano calibrado {_fmt(cal['reserves_rmse_median'], 0)} USD M "
            f"contra {_fmt(cal['reserves_rmse_persistence'], 0)} USD M del baseline de "
            "persistencia (congelar el nivel de 1998-01). Fracción con "
            f"`sovereign_default`/`collapse` en meses 36-54: "
            f"{_fmt_pct(cal['default_or_collapse_fraction'])} "
            f"(IC95 {_fmt_pct_ci(cal['default_or_collapse_fraction_ci'])}). Ver la tabla de "
            "Resumen para el veredicto formal y `results.json` para la trayectoria completa de "
            "reservas.",
            "",
        ]
    lines += ["### V3 — inflación y elecciones (in-sample, ver registro)", ""]
    v3 = by_id.get("V3")
    if v3:
        cal = v3.metrics_by_arm["calibrated"]
        aur = v3.metrics_by_arm["aurora"]
        applied = (
            ", ".join(f"`{row['shock_id']}` {row['date']}" for row in v3.plan.applied_rows)
            or "ninguno"
        )
        v3_runs = v3.runs_by_arm["calibrated"]
        appr0 = statistics.median([r.government_approval[0] for r in v3_runs])
        appr_last = statistics.median([r.government_approval[-1] for r in v3_runs])
        n_collapse = cal["outcomes"].get("collapse", 0)
        lines += [
            "**Esta ventana (2016-01 + 96 meses) cae DENTRO del train de la calibración "
            "(`1992-01:2023-12`, A5) -- es in-sample, no una prueba de generalización** (ver "
            "`registration.json -> tests[].sample_declaration`). Un ajuste aquí puede reflejar "
            "sobreajuste al propio período, no una propiedad general del modelo.",
            "",
            f"Shocks exógenos forzados: {applied}. Inflación anualizada final (mediana): "
            f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} (calibrado) vs "
            f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} (Aurora), contra ~135 % "
            "anual real en 2023 (Banco Mundial). Canal electoral (aprobación→cohortes→voto, "
            "sin cambios de ADR 012): aprobación mediana cae de "
            f"{appr0:.0f} (2016-01) a {appr_last:.0f} (fin de corrida); oficialismo pierde en "
            f"2019-12 en {_fmt_pct(cal['elections']['2019-12']['hit_fraction'])} de semillas "
            f"calibradas vs {_fmt_pct(aur['elections']['2019-12']['hit_fraction'])} de Aurora. "
            f"`collapse` en {n_collapse} de {sum(cal['outcomes'].values())} semillas "
            "calibradas -- donde hay `collapse` la elección de 2023 no se celebra (ver "
            "`elections['2023-12'].n_held` en `results.json`, denominador real del acierto "
            "electoral de esa fecha).",
            "",
        ]
    lines += ["### V4 — oficialismo y partidos por época (ADR 013)", ""]
    v4 = by_id.get("V4")
    if v4:
        cal = v4.metrics_by_arm["calibrated"]
        aur = v4.metrics_by_arm["aurora"]
        n_cal_total = sum(cal["outcomes"].values())
        n_cal_ended_early = cal["outcomes"].get("collapse", 0) + cal["outcomes"].get(
            "hyperinflation", 0
        )
        lines += [
            "Corrida desde 2019-12 con los partidos/actores/lealtades de la época 2015-2023 "
            "(ADR 013, integrado en paralelo -- LLA con `founded 2021`/`outsider_bonus`), NO "
            "los 29 actores fijos de Aurora. Inflación anualizada final (mediana): "
            f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} (calibrado) vs "
            f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} (Aurora), contra ~211 % "
            "anual real dic-2023 (INDEC, diciembre contra diciembre). Derrota electoral "
            f"(cualquier elección de la ventana): {_fmt_pct(cal['election_defeat_fraction'])} "
            f"(calibrado) vs {_fmt_pct(aur['election_defeat_fraction'])} (Aurora). Semillas "
            f"calibradas que terminan antes de los {v4.months} meses "
            f"(`collapse`/`hyperinflation`): {n_cal_ended_early} de {n_cal_total} -- si esa "
            "fracción es alta, la hipótesis electoral no se puede evaluar con la misma "
            "confianza que la de inflación (la corrida termina antes de que se celebre la "
            "elección de fin de mandato).",
            "",
        ]
    lines += [
        "### Lo transversal",
        "",
        "A diferencia de A4 (ADR 011), el motor con macro activo SI tiene los mecanismos no "
        "lineales que las tres pruebas necesitan (indexación que se acelera con la inflación, "
        "un régimen cambiario que puede romperse, reservas con balance de pagos real) -- ver "
        "los veredictos de la tabla de Resumen para si la MAGNITUD calibrada alcanza los "
        "umbrales registrados. Calibrar 155 coeficientes (97 económicos + 58 macro) sobre "
        "`1992-01:2023-12` no garantiza que los umbrales se crucen: los tres episodios "
        "extremos argentinos son eventos de cola, y la pérdida agregada (RMSE o cola pesada) "
        "puede preferir un ajuste que promedie bien sobre TODO el período en vez de uno que "
        "acierte los extremos.",
        "",
    ]
    return lines


def _lessons_section_legacy(results: list[ValidationResult]) -> list[str]:
    """Explicacion MECANICA de por que el modelo reprodujo (o no) cada
    episodio, para una calibracion SIN macro (ADR 011, p.ej. `a3_main`).
    Los numeros que se citan salen de los coeficientes en disco
    (`country.json` vs `calibration/a3_main/coefficients.json`) y de las
    ecuaciones de `world/economy.py`, no de la narrativa del resultado. SIN
    CAMBIOS de contenido respecto de A4 (ver `_lessons_section_macro` para
    la version con `macro_coefficients`)."""
    by_id = {r.test_id: r for r in results}
    persist = inflation_persistence()
    lines = ["## Qué aprendimos del modelo", "", "### V1 — por qué NO hay hiperinflación", ""]
    v1 = by_id.get("V1")
    if v1:
        cal = v1.metrics_by_arm["calibrated"]
        aur = v1.metrics_by_arm["aurora"]
        lines += [
            "La ecuación de inflación de `world/economy.py::step_economy` (§4.3) es "
            "`π_{t+1} = ρ_π·π_t + c_e·de_t + c_g·demand_gap + c_f·pos(déficit−2) − c_r·r_gap/100`, "
            "y el tipo de cambio (§4.2) es `de_t ≈ π_t − π_mundo + b_res·reserves_gap − "
            "b_r·r_gap/100 + b_conf·(...)`. Sustituyendo, **el coeficiente total sobre la "
            "inflación del mes anterior es `ρ_π + c_e`**: "
            f"{persist['aurora_rho_pi']:.3f} + {persist['aurora_c_e']:.3f} = "
            f"**{persist['aurora_total']:.3f}** en Aurora y "
            f"{persist.get('calibrated_rho_pi', float('nan')):.3f} + "
            f"{persist.get('calibrated_c_e', float('nan')):.3f} = "
            f"**{persist.get('calibrated_total', float('nan')):.3f}** con los coeficientes "
            "calibrados. Los dos son < 1, así que "
            "la ecuación es una *contracción*: desde cualquier estado inicial la inflación "
            "converge monótonamente a un punto fijo en vez de explotar. Una hiperinflación "
            "endógena es **algebraicamente imposible** en este motor sin un `shock_pi` grande y "
            "sostenido; el único camino al `outcome = hyperinflation` (π > 20 %/mes tres meses "
            "seguidos) es forzar un shock — exactamente lo que el ADR prohíbe en V1.",
            "",
            "Empíricamente: arrancando de 13.99 %/mes real de 1988-06, la inflación mensual "
            f"mediana al mes {v1.months} es "
            f"{_fmt(cal['inflation_monthly_final_median'], 2, ' %')} "
            f"(calibrado) y {_fmt(aur['inflation_monthly_final_median'], 2, ' %')} (Aurora); "
            "la real de 1989 fue ~33 %/mes (3046 % anual, Banco Mundial). El término que domina "
            "no es ninguno de los canales de crisis: es la **reversión a la media de la propia "
            "inercia inflacionaria**, con `de` siguiendo pasivamente a π y `r_gap` clavado cerca "
            "de 0 porque `PassivePolicy` ajusta la tasa nominal para sostener la tasa real "
            "neutral (r_real ≈ 6 %, r_gap ≈ 2 en el mes 1) — es decir, el modelo supone un banco "
            "central que indexa la tasa a la inflación, lo contrario de la Argentina de 1988.",
            "",
            "**La calibración empeora esto.** A3 movió `ρ_π` de "
            f"{persist['aurora_rho_pi']:.3f} a "
            f"{persist.get('calibrated_rho_pi', float('nan')):.3f} (el mayor cambio "
            "estructural de todo el vector), porque se ajustó sobre 1993–2015: convertibilidad "
            "más post-2003, un período en el que la inflación mensual *es* fuertemente reversiva. "
            "El resultado es un modelo que revierte todavía más rápido y queda todavía más "
            "lejos de 1989: ninguno de los dos brazos llega a `hyperinflation` "
            f"({_fmt_pct(cal['hyperinflation_fraction'])} de semillas calibradas y "
            f"{_fmt_pct(aur['hyperinflation_fraction'])} de Aurora), pero el calibrado termina "
            f"en {_fmt(cal['inflation_monthly_final_median'], 2, ' %')}/mes contra "
            f"{_fmt(aur['inflation_monthly_final_median'], 2, ' %')}/mes de Aurora, con la "
            "real en ~33 %/mes. Es el mismo sobreajuste que el reporte de A3 ya había "
            "detectado en el "
            "holdout de inflación (RMSE normalizado 1.26 calibrado vs 0.71 persistencia a 12 "
            "meses), visto desde otro ángulo.",
            "",
        ]
    lines += ["### V2 — por qué el peg no hace caer las reservas", ""]
    v2 = by_id.get("V2")
    if v2:
        cal = v2.metrics_by_arm["calibrated"]
        inert = v2.diagnostics.get("fx_regime_inertness", {})
        verdict = (
            "idénticas estado a estado con la misma semilla"
            if inert.get("trajectories_identical")
            else "NO idénticas (ver `results.json`)"
        )
        lines += [
            "**`--fx-regime peg` es inerte en esta implementación.** `fx_regime` solo se lee en "
            "un lugar del motor, `world/bimonetary.py::step_bimonetary`, y solo para decidir si "
            '`fx_gap > 0` (`fx_regime == "control"`). No entra en `step_economy`: no fija `de`, '
            "no obliga a intervenir, no consume reservas. El ADR 011 §5 decía que «la "
            "convertibilidad es `peg` con `fx_intervention = 1` y `k_k` alto mientras haya "
            "reservas», y eso **no se implementó** en A2. Verificado empíricamente en esta "
            f"corrida ({inert.get('seeds', 0)} semillas, diagnóstico `fx_regime_inertness` de "
            f"`results.json`): las trayectorias con `--fx-regime peg` y con `--fx-regime float` "
            f"son {verdict}. La pregunta «¿colapsa con convertibilidad rígida?» no "
            "se puede responder porque el modelo no tiene convertibilidad.",
            "",
            "Tampoco hay realimentación del bloque bimonetario hacia el núcleo: el ADR 011 §5 "
            "pedía `de_raw += x_d · dollar_demand`, y ese término no existe en `world/economy.py`. "
            "`dollar_demand`, `fx_gap`, `external_debt_usd` y `default_risk` se calculan "
            "*después* de `advance_month` y nunca vuelven a entrar en las 20 variables. El bloque "
            "externo es hoy un **lector**, no un mecanismo.",
            "",
            "Las reservas (§4.7) son "
            "`R_{t+1} = R_t + k_tb·(commodity−100) + k_w·(wd−100) + k_k·clamp(r_gap) − "
            "k_conf·pos(conf_neutral−conf) − intervención`: una **caminata con deriva, sin ancla "
            "de nivel**. `reserves_target` (10 000 USD M, valor de Aurora) solo entra vía "
            "`reserves_gap = pos(target − R)/target`, que con las reservas reales de 1998 "
            "(27 914 USD M) vale **0 todos los meses**: no hay ningún término que empuje las "
            "reservas hacia abajo cuando están «altas». Con `r_gap ≈ 2` sostenido por "
            "`PassivePolicy`, `k_k·r_gap ≈ +24 USD M/mes` es deriva positiva. Por eso el modelo "
            f"deja las reservas casi planas ({_v2_reserves_range(v2)}) mientras la serie real "
            "cae de 27 914 (1998-01) a ~10 000 (2002-06): RMSE mediano "
            f"{_fmt(cal['reserves_rmse_median'], 0)} USD M contra "
            f"{_fmt(cal['reserves_rmse_persistence'], 0)} USD M del baseline ingenuo de "
            "congelar el nivel real de 1998-01 — es decir, después de calibrar 107 "
            "coeficientes el modelo describe la caída de las reservas de la convertibilidad "
            "apenas mejor que suponer que no pasó nada.",
            "",
            "Y el `sovereign_default` endógeno nunca se dispara: `default_risk = "
            "0.55·pos(deuda/reservas − 1) + 0.011·pos(déficit)` se queda en ~0.03–0.10 contra un "
            "umbral de 0.54, justamente porque las reservas no caen. El canal existe, pero su "
            "entrada nunca se mueve.",
            "",
        ]
    lines += ["### V3 — la inflación no se acelera, pero el modelo sí castiga al oficialismo", ""]
    v3 = by_id.get("V3")
    if v3:
        cal = v3.metrics_by_arm["calibrated"]
        aur = v3.metrics_by_arm["aurora"]
        applied = (
            ", ".join(f"`{row['shock_id']}` {row['date']}" for row in v3.plan.applied_rows)
            or "ninguno"
        )
        v3_runs = v3.runs_by_arm["calibrated"]
        appr0 = statistics.median([r.government_approval[0] for r in v3_runs])
        appr_last = statistics.median([r.government_approval[-1] for r in v3_runs])
        n_collapse = cal["outcomes"].get("collapse", 0)
        end_date = month_date("2016-01", int(cal["median_months_run"]))
        lines += [
            "Mismo mecanismo que V1 por el lado de los precios: con `ρ_π + c_e = "
            f"{persist.get('calibrated_total', float('nan')):.2f}` la "
            f"inflación no puede acelerarse sola, y los shocks que sí se aplicaron ({applied}) "
            "son shocks de **actividad y fiscales**, no "
            "de precios. La mediana de inflación anualizada final es "
            f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} (calibrado) y "
            f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} (Aurora) contra 135 % anual "
            "real en 2023 (Banco Mundial; ~211 % diciembre contra diciembre según INDEC). Otra "
            "vez la calibración se aleja más de la historia que Aurora.",
            "",
            "**Lo que sí funciona es el castigo electoral.** En 2019-12 (mes 48, el múltiplo de "
            "`term_length` que el motor usa; no la fecha real de octubre) el oficialismo pierde "
            f"en {_fmt_pct(cal['elections']['2019-12']['hit_fraction'])} de las semillas "
            f"calibradas contra {_fmt_pct(aur['elections']['2019-12']['hit_fraction'])} en "
            "Aurora, y no por la inflación sino por el canal aprobación→cohortes→voto: la "
            f"aprobación de gobierno (mediana) cae de {appr0:.0f} en 2016-01 a "
            f"{appr_last:.0f} al final de la corrida, arrastrada por "
            "`social_tension` creciente y `protest_level` alto, y las cohortes votan contra el "
            "oficialismo. Es el resultado del que más se puede decir que el modelo «acertó».",
            "",
            "El precio de ese mismo canal es que **la corrida calibrada casi no llega a 2023**: "
            "la espiral aprobación↓ → tensión↑ → estabilidad↓ cruza el umbral terminal "
            "(`political_stability < 15` tres meses seguidos) alrededor del mes "
            f"{_fmt(cal['median_months_run'], 0)} (mediana), es decir {end_date}, y la "
            f"simulación termina en `collapse` en {n_collapse} de "
            f"{sum(cal['outcomes'].values())} semillas. Donde hay `collapse` la elección de 2023 "
            "nunca ocurre, así que ese «acierto electoral» mide supervivencia, no elección del "
            f"ganador: la elección de 2023-12 se celebró en "
            f"{cal['elections']['2023-12']['n_held']} de {sum(cal['outcomes'].values())} "
            "semillas calibradas y en "
            f"{aur['elections']['2023-12']['n_held']} de {sum(aur['outcomes'].values())} de "
            f"Aurora, que acierta 2023 en "
            f"{_fmt_pct(aur['elections']['2023-12']['hit_fraction'])} de las semillas.",
            "",
        ]
    lines += [
        "### Lo transversal",
        "",
        "Los tres episodios que definen la macro argentina —hiperinflación, corrida con tipo de "
        "cambio fijo y default— dependen de **no linealidades y de restricciones de balance** "
        "(indexación explosiva, una regla cambiaria que se rompe, un stock de reservas que se "
        "agota) que este motor no tiene: sus 20 variables se mueven con ecuaciones lineales, "
        "estables y con reversión a la media, y los únicos saltos discretos son los shocks del "
        "catálogo, que hay que forzar desde afuera. Calibrar los ~107 coeficientes sobre "
        "1993–2015 no cambia esa arquitectura: mueve el punto fijo, no la estabilidad del "
        "sistema. Lo que el modelo sí reproduce es **dinámica política lenta**: desgaste de "
        "aprobación, tensión social acumulada y alternancia electoral.",
        "",
    ]
    return lines


def _cannot_conclude_section(results: list[ValidationResult], calibration_run_id: str) -> list[str]:
    """Dispatcher A5 (ADR 012 secc. 6): mismo criterio que `_lessons_
    section` -- los puntos 2/3 de la version legacy afirman cosas que son
    FALSAS con macro activo (`peg` SI tiene efecto, la ecuacion operativa
    de precios NO es `rho_pi + c_e`), asi que no se reusan tal cual."""
    if macro_price_mechanism(calibration_run_id) is not None:
        return _cannot_conclude_section_macro(results)
    return _cannot_conclude_section_legacy(results)


def _cannot_conclude_section_macro(results: list[ValidationResult]) -> list[str]:
    by_id: dict[str, ValidationResult] = {r.test_id: r for r in results}
    lines = [
        "## Qué NO se puede concluir",
        "",
        "1. **Nada sobre la Argentina real.** Estas corridas dicen cómo se comporta República "
        "Artificial calibrada con datos argentinos. Una hipótesis NO CUMPLIDA es evidencia "
        "sobre el modelo, no sobre la historia.",
        "2. **Que un veredicto NO CUMPLIDO signifique que el mecanismo sigue roto.** A "
        "diferencia de A4 (ADR 011), `rho_eff`/`fx_regime`/balance de pagos (ADR 012) SI "
        "afectan la simulación (ver `_lessons_section_macro` arriba y los tests de "
        "`tests/test_macro_regime.py`, que verifican el mecanismo de forma aislada); si una "
        "hipótesis no se cumple igual, es una cuestión de MAGNITUD/calibración, no de que el "
        "canal no exista.",
        "3. **Que V3 (2016→2023) mida generalización.** Esta ventana está DENTRO del train de "
        "la calibración (`1992-01:2023-12`) -- es in-sample (ver "
        "`registration.json -> tests[].sample_declaration`). Solo V1 (1988→1990) está en el "
        "holdout real de esta calibración.",
    ]
    v2 = by_id.get("V2")
    if v2 and v2.plan.unmatched:
        lines.append(
            "4. **Que el modelo «no reprodujo 2001 pese a la crisis rusa/brasileña».** Esa crisis "
            "**no se aplicó**: `politics/shocks_calendar.csv` (dato de A1) no tiene ninguna fila "
            "entre 1995-01 y 2003-01 — ni la crisis internacional de 1998–99 que pide el ADR, ni "
            "el corralito/default de diciembre de 2001 que `PLAN_ARGENTINA.md` §1 lista como "
            "shock histórico. No se agregó la fila para que la prueba «diera» "
            "(PLAN_ARGENTINA.md §0.1): V2 corrió con cero shocks forzados y eso es lo que mide."
        )
    else:
        lines.append(
            "4. **Que los shocks forzados expliquen el resultado.** Los forzados están listados "
            "prueba por prueba arriba; un episodio reproducido en un mes con shock forzado no es "
            "mérito de la dinámica interna."
        )
    lines += [
        "5. **Que el modelo «falle» la elección de 2023 en el brazo calibrado.** En las "
        "semillas que terminan en `collapse` antes del mes 96 la elección no llega a ocurrir: "
        "ese acierto mide supervivencia, no capacidad predictiva electoral.",
        "6. **Que las elecciones del modelo sean las elecciones reales.** El motor las pone en "
        "múltiplos de `term_length` desde `--start` (2019-12 y 2023-12), no en octubre de 2019 y "
        "2023, y no tiene noción de qué partido sintético corresponde a qué lista real: se "
        "compara sólo `reelected`/`defeated` (misma simplificación declarada en A3).",
        "7. **Que estos números se generalicen a otras semillas o ventanas.** Los IC 95 % son "
        "bootstrap sobre las semillas de ESTA corrida: cubren la variabilidad de Monte Carlo, no "
        "la incertidumbre del estado inicial (con 9–15 de 21 variables `assumed`), ni la de los "
        "coeficientes, ni la del calendario de shocks.",
        "8. **Que un `collapse` del motor sea «una crisis argentina».** `collapse` es "
        "`political_stability < 15` durante 3 meses, un umbral de diseño de Aurora sin "
        "calibración contra ningún evento histórico.",
        "",
    ]
    return lines


def _cannot_conclude_section_legacy(results: list[ValidationResult]) -> list[str]:
    """Version ORIGINAL de A4 (ADR 011, sin macro) -- SIN CAMBIOS de
    contenido, ver `_cannot_conclude_section` (dispatcher) y
    `_cannot_conclude_section_macro`."""
    by_id: dict[str, ValidationResult] = {r.test_id: r for r in results}
    lines = [
        "## Qué NO se puede concluir",
        "",
        "1. **Nada sobre la Argentina real.** Estas corridas dicen cómo se comporta un motor de "
        "20 ecuaciones con coeficientes ajustados a series argentinas. Una hipótesis NO CUMPLIDA "
        "es evidencia sobre el modelo, no sobre la historia.",
        "2. **Que «el modelo no puede tener hiperinflación» sea un hecho sobre la inflación "
        "argentina.** Es un hecho sobre `ρ_π + c_e < 1` en `world/economy.py`, una propiedad de "
        "la especificación elegida en Aurora (ADR 001/002) y heredada sin revisión por el "
        "paquete de país.",
        "3. **Que la convertibilidad «no importaba».** V2 no testeó la convertibilidad: "
        "`--fx-regime peg` no tiene ningún efecto en el motor de hoy (verificado: `peg` y "
        "`float` dan trayectorias idénticas). El resultado de V2 es un resultado sobre un "
        "régimen de flotación con el estado inicial de 1998.",
    ]
    v2 = by_id.get("V2")
    if v2 and v2.plan.unmatched:
        lines.append(
            "4. **Que el modelo «no reprodujo 2001 pese a la crisis rusa/brasileña».** Esa crisis "
            "**no se aplicó**: `politics/shocks_calendar.csv` (dato de A1) no tiene ninguna fila "
            "entre 1995-01 y 2003-01 — ni la crisis internacional de 1998–99 que pide el ADR, ni "
            "el corralito/default de diciembre de 2001 que `PLAN_ARGENTINA.md` §1 lista como "
            "shock histórico. No se agregó la fila para que la prueba «diera» "
            "(PLAN_ARGENTINA.md §0.1): V2 corrió con cero shocks forzados y eso es lo que mide."
        )
    else:
        lines.append(
            "4. **Que los shocks forzados expliquen el resultado.** Los forzados están listados "
            "prueba por prueba arriba; un episodio reproducido en un mes con shock forzado no es "
            "mérito de la dinámica interna."
        )
    lines += [
        "5. **Que el modelo «falle» la elección de 2023 en el brazo calibrado.** En las "
        "semillas que terminan en `collapse` antes del mes 96 la elección no llega a ocurrir: "
        "ese acierto mide supervivencia, no capacidad predictiva electoral.",
        "6. **Que las elecciones del modelo sean las elecciones reales.** El motor las pone en "
        "múltiplos de `term_length` desde `--start` (2019-12 y 2023-12), no en octubre de 2019 y "
        "2023, y no tiene noción de qué partido sintético corresponde a qué lista real: se "
        "compara sólo `reelected`/`defeated` (misma simplificación declarada en A3).",
        "7. **Que estos números se generalicen a otras semillas o ventanas.** Los IC 95 % son "
        "bootstrap sobre las semillas de ESTA corrida: cubren la variabilidad de Monte Carlo, no "
        "la incertidumbre del estado inicial (con 9–15 de 21 variables `assumed`), ni la de los "
        "coeficientes, ni la del calendario de shocks.",
        "8. **Que un `collapse` del motor sea «una crisis argentina».** `collapse` es "
        "`political_stability < 15` durante 3 meses, un umbral de diseño de Aurora sin "
        "calibración contra ningún evento histórico.",
        "",
    ]
    return lines
