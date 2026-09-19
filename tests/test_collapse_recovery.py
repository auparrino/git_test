"""ADR 016 — piso de estabilidad por legitimidad democratica.

Cubre los cinco puntos que el ADR registra como hipotesis (secc. 3):

1. **Flag off = golden intacto.** El golden de Aurora sin `--country` sigue
   byte a byte igual, y una corrida de Argentina con `legitimacy_floor=False`
   reproduce el `collapse` de 2019-12 que documenta el diagnostico (secc. 2):
   el mecanismo nuevo no toca NADA con el flag apagado.
2. **2019-12 (H1/H2)**: con el piso, >= 60 % de las semillas llegan al mes 48
   (la eleccion de fin de mandato se celebra) sin que la inflacion se
   desplome.
3. **1998-01 con `peg` (H3)**: el colapso SIGUE ocurriendo en >= 50 % de las
   semillas. Es la prueba que impide que el mecanismo sea una amnistia
   general: el modelo tiene que seguir distinguiendo 2001 de 2020.
4. **Compuerta de ruptura**: unit tests directos sobre las funciones puras
   de `world/events.py`.
5. Los seis tests de ADR 012 secc. 7 viven en `tests/test_macro_regime.py` y
   siguen verdes sin cambios (medido: los cuatro escenarios estocasticos dan
   resultados IDENTICOS con y sin el piso, porque en todos ellos o hay
   ruptura activa o no hay colapso que evitar -- ver las Notas de
   implementacion del ADR 016).

Nota sobre 2001-01: `data/countries/argentina/country.json` no trae
`initial_states` para esa fecha (las ocho disponibles son 1983-12, 1988-06,
1991-04, 1998-01, 2003-06, 2016-01, 2019-12 y 2023-12), asi que el
discriminante "2001" se mide desde **1998-01 con `peg` y 54 meses** -- la
configuracion de V2, cuya ventana termina exactamente en 2002-06. No se
invento un estado inicial (ADR 016 secc. 3, nota).
"""

from __future__ import annotations

import hashlib
import json

from republica.engine.simulation import run
from republica.validation.argentina import TESTS_BY_ID, resolve_forced_shocks, run_test_arm
from republica.world.config import load_country
from republica.world.countries import load_country_pack
from republica.world.economy import LEGITIMACY_FIELDS, MacroCoefficients
from republica.world.events import (
    LegitimacyContext,
    apply_legitimacy_floor,
    legitimacy_rupture_active,
    legitimacy_stability_floor,
)

CALIBRATION = "a5b_macro"
N_SEEDS = 10

#: Mismo golden (y misma corrida) que
#: `tests/test_country_pack_argentina.py::
#: test_aurora_without_country_matches_golden_hash_pre_a2`. Se repite aca a
#: proposito: ese test protege a ADR 011/012, este protege a ADR 016 y tiene
#: que fallar por si solo si alguien prende el piso para Aurora por error.
GOLDEN_SEED7_NO_COUNTRY_SHA256 = "b4bbfe09e6bb0a6b0b7e66306e0dc99b664592411a613d62947581b342e5013a"


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 1. Flag off: nada cambia.
# ---------------------------------------------------------------------------


def test_aurora_golden_hash_unchanged_by_adr_016() -> None:
    """Aurora no declara `features.legitimacy_floor` y ademas corre sin
    `macro_coefficients`: el doble gate de `run()` deja el piso apagado."""
    history = run(
        seed=7,
        months=48,
        country=load_country(),
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    digest = hashlib.sha256(_strip_config_hash(history.to_jsonl()).encode("utf-8")).hexdigest()
    assert digest == GOLDEN_SEED7_NO_COUNTRY_SHA256


def test_legitimacy_floor_is_off_for_aurora_country_features() -> None:
    assert load_country().features.get("legitimacy_floor", False) is False


def test_legitimacy_floor_is_on_for_the_argentina_pack() -> None:
    pack = load_country_pack("argentina", "2019-12", 48)
    assert pack.country.features.get("legitimacy_floor") is True
    assert pack.country.features.get("macro_regime") is True


def _v4_runs(seeds: int, *, arm: str = "calibrated", legitimacy_floor: bool | None = None):
    """Brazo de V4 (2019-12, 48 meses) por el MISMO camino que
    `republica validate`: estado inicial real, shocks forzados del ADR,
    exogenas historicas, partidos de la epoca 2015-2023."""
    test = TESTS_BY_ID["V4"]
    pack = load_country_pack("argentina", test.start, test.months)
    plan = resolve_forced_shocks(pack.pack_dir, test, test.months)
    return run_test_arm(
        test,
        arm,
        pack,
        plan,
        test.months,
        seeds,
        1,
        CALIBRATION,
        legitimacy_floor=legitimacy_floor,
    )


def test_flag_off_still_collapses_from_2019_12_as_diagnosed() -> None:
    """El diagnostico de ADR 016 secc. 2 medido como test: con el piso
    apagado, 2019-12 sigue colapsando en TODAS las semillas antes del mes 48.
    Si este test empieza a fallar es que alguien cambio el comportamiento
    base, no el de ADR 016."""
    runs = _v4_runs(N_SEEDS, legitimacy_floor=False)
    assert all(r.outcome == "collapse" for r in runs), [r.outcome for r in runs]
    assert all(r.months_run < 48 for r in runs), [r.months_run for r in runs]


# ---------------------------------------------------------------------------
# 2. H1/H2: desde 2019-12 la eleccion de fin de mandato se celebra.
# ---------------------------------------------------------------------------


def test_2019_12_reaches_month_48_in_most_seeds_with_the_floor() -> None:
    runs = _v4_runs(N_SEEDS, legitimacy_floor=True)
    reached = sum(1 for r in runs if r.months_run >= 48)
    assert reached / N_SEEDS >= 0.6, (
        f"solo {reached}/{N_SEEDS} semillas llegan al mes 48 desde 2019-12 "
        "(ADR 016 secc. 3, H1: >= 60 %)"
    )


def test_2019_12_still_ends_with_high_inflation() -> None:
    """H2: el piso NO es una forma encubierta de estabilizar la economia --
    la inflacion final sigue siendo de tres digitos anualizados."""
    runs = _v4_runs(N_SEEDS, legitimacy_floor=True)
    annual_values = sorted(r.inflation_annual_final for r in runs)
    annual = annual_values[len(annual_values) // 2]
    assert annual > 80.0, (
        f"inflacion anualizada final mediana {annual:.1f} % (ADR 016 secc. 3, H2: > 80 %)"
    )


def test_2019_12_holds_the_end_of_term_election_with_the_floor() -> None:
    runs = _v4_runs(N_SEEDS, legitimacy_floor=True)
    with_election = sum(1 for r in runs if r.elections)
    assert with_election / N_SEEDS >= 0.6, (
        f"solo {with_election}/{N_SEEDS} semillas celebran la eleccion de fin de mandato"
    )


# ---------------------------------------------------------------------------
# 3. H3: el discriminante. 2001 tiene que seguir colapsando.
# ---------------------------------------------------------------------------


def _peg_1998_runs(seeds: int, *, legitimacy_floor: bool | None):
    test = TESTS_BY_ID["V2"]  # 1998-01, 54 meses (la ventana termina en 2002-06)
    pack = load_country_pack("argentina", test.start, test.months)
    plan = resolve_forced_shocks(pack.pack_dir, test, test.months)
    return run_test_arm(
        test,
        "calibrated",
        pack,
        plan,
        test.months,
        seeds,
        1,
        CALIBRATION,
        legitimacy_floor=legitimacy_floor,
    )


def test_1998_01_peg_still_collapses_before_2002_06_with_the_floor() -> None:
    """H3 (ADR 016 secc. 3): el mecanismo tiene que DISTINGUIR 2001 de 2020,
    no eliminar el colapso. La salida forzada de la convertibilidad
    (`fx_regime_exit`) suspende el piso por el resto del mandato."""
    runs = _peg_1998_runs(N_SEEDS, legitimacy_floor=True)
    collapsed = sum(1 for r in runs if r.outcome == "collapse")
    assert collapsed / N_SEEDS >= 0.5, (
        f"solo {collapsed}/{N_SEEDS} semillas colapsan desde 1998-01 con `peg` "
        "(ADR 016 secc. 3, H3: >= 50 % -- el piso no puede ser una amnistia general)"
    )


def test_the_floor_does_not_change_the_1998_01_peg_scenario_at_all() -> None:
    """Mas fuerte que H3: en ese escenario el piso esta suspendido TODO el
    tiempo (la salida del peg ocurre en las 10 semillas), asi que los
    outcomes son identicos con y sin el flag."""
    off = _peg_1998_runs(N_SEEDS, legitimacy_floor=False)
    on = _peg_1998_runs(N_SEEDS, legitimacy_floor=True)
    assert [(r.outcome, r.months_run) for r in off] == [(r.outcome, r.months_run) for r in on]


# ---------------------------------------------------------------------------
# 4. Compuerta de ruptura y forma del piso (unit, funciones puras).
# ---------------------------------------------------------------------------


def _ctx(**kw) -> LegitimacyContext:
    base = dict(
        month=12,
        last_election_month=0,
        term_length=48,
        repression=0.0,
        high_inflation_months=0,
        banking_crisis=False,
        sovereign_default=False,
        months_since_fx_exit=None,
    )
    base.update(kw)
    return LegitimacyContext(**base)


def test_floor_decays_from_lf_base_to_lf_min_across_the_term() -> None:
    c = MacroCoefficients()
    start = legitimacy_stability_floor(_ctx(month=1), c)
    end = legitimacy_stability_floor(_ctx(month=48), c)
    assert start > end
    assert start <= c.lf_base
    assert end == c.lf_min
    # Los dos extremos quedan por encima del umbral de colapso de Argentina.
    assert end > 15.0


def test_floor_is_zero_outside_democracy_and_without_a_mandate() -> None:
    c = MacroCoefficients()
    assert legitimacy_stability_floor(_ctx(repression=0.85), c) == 0.0
    assert legitimacy_stability_floor(_ctx(term_length=0), c) == 0.0


def test_each_rupture_marker_suspends_the_floor() -> None:
    c = MacroCoefficients()
    assert not legitimacy_rupture_active(_ctx(), c)
    assert legitimacy_rupture_active(_ctx(high_inflation_months=c.lf_rupture_months), c)
    assert legitimacy_rupture_active(_ctx(banking_crisis=True), c)
    assert legitimacy_rupture_active(_ctx(sovereign_default=True), c)
    assert legitimacy_rupture_active(_ctx(months_since_fx_exit=1), c)
    # Justo por debajo del umbral de persistencia: todavia no es ruptura.
    assert not legitimacy_rupture_active(_ctx(high_inflation_months=c.lf_rupture_months - 1), c)
    for ctx in (
        _ctx(banking_crisis=True),
        _ctx(sovereign_default=True),
        _ctx(months_since_fx_exit=1),
    ):
        assert legitimacy_stability_floor(ctx, c) == 0.0


def test_apply_floor_only_raises_stability_and_never_lowers_it() -> None:
    c = MacroCoefficients()
    pack = load_country_pack("argentina", "2019-12", 48)
    state = pack.country.initial_state
    low = state.model_copy(update={"political_stability": 3.0})
    raised = apply_legitimacy_floor(low, _ctx(month=1), c)
    assert raised.political_stability == legitimacy_stability_floor(_ctx(month=1), c)
    high = state.model_copy(update={"political_stability": 90.0})
    assert apply_legitimacy_floor(high, _ctx(month=1), c) is high


# ---------------------------------------------------------------------------
# 5. Los `lf_*` son estructurales: fuera del vector de calibracion.
# ---------------------------------------------------------------------------


def test_legitimacy_coefficients_are_not_calibration_tunable() -> None:
    from republica.calibration.parameters import MACRO_TUNABLE

    assert not set(LEGITIMACY_FIELDS) & set(MACRO_TUNABLE)


def test_legitimacy_coefficients_of_the_pack_survive_a_calibration() -> None:
    """`coefficients.json` de una calibracion no trae los `lf_*`; el brazo
    calibrado tiene que tomarlos igual del paquete de pais (ver
    `world/economy.py::merge_structural_coefficients`)."""
    from republica.calibration.run import load_calibrated_country

    pack = load_country_pack("argentina", "2019-12", 48)
    _, _, calibrated_macro = load_calibrated_country("argentina", CALIBRATION)
    assert calibrated_macro is not None
    from republica.world.economy import merge_structural_coefficients

    merged = merge_structural_coefficients(calibrated_macro, pack.macro_coefficients)
    for name in LEGITIMACY_FIELDS:
        assert getattr(merged, name) == getattr(pack.macro_coefficients, name)
