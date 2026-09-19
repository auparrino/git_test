"""Tests de la sonda exploratoria (ADR 020 secc. 6).

Todo por debajo de 60 s: el unico test que corre el modelo usa un escenario
chico (2 semillas, 12 meses); los demas miden las funciones de deteccion
sobre series sinteticas, sin simular nada.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from republica.cli import app
from republica.probe.report import build_report
from republica.probe.runner import (
    PHYSICAL_RANGES,
    ProbeScenario,
    detect_physical_violations,
    detect_saturation,
    load_scenarios,
    run_probe,
    scenarios_path,
)

runner = CliRunner()

SMALL_CSV = 'label,start,months,expected\nchico,2015-12,12,"escenario chico de prueba"\n'


def _write_scenarios(tmp_path, body: str):
    path = tmp_path / "probe_scenarios.csv"
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 1. Punta a punta por CLI sobre un escenario chico.
# --------------------------------------------------------------------------


def test_probe_cli_end_to_end_small_scenario(tmp_path) -> None:
    scen = _write_scenarios(tmp_path, SMALL_CSV)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "probe",
            "--country",
            "argentina",
            "--run-id",
            "test",
            "--seeds",
            "2",
            "--scenarios",
            str(scen),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    report = out / "report.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    # El reporte tiene que decir que NO es un backtest ni una validacion.
    assert "no es un backtest ni una validación" in text
    assert "Saturación contra la cota" in text
    assert "Valores fuera de rango físico" in text
    assert "escenario chico de prueba" in text

    payload = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert payload["seeds"] == 2
    assert len(payload["scenarios"]) == 1
    sc = payload["scenarios"][0]
    assert sc["label"] == "chico"
    assert sc["seeds_run"] == 2
    assert sc["end_month_median"] is not None

    # Un CSV por semilla-escenario, con una fila por mes.
    csvs = sorted((out / "series").glob("chico__seed*.csv"))
    assert len(csvs) == 2
    lines = csvs[0].read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("month,date,")
    assert "government_approval" in lines[0]
    assert 2 <= len(lines) <= 13  # cabecera + hasta 12 meses


# --------------------------------------------------------------------------
# 2. Deteccion de saturacion.
# --------------------------------------------------------------------------


def test_detect_saturation_flags_a_pinned_variable_and_not_a_free_one() -> None:
    ranges = {
        "government_approval": (0.0, 100.0),
        "inflation": (-1.0, 60.0),
    }
    series = {
        # Toca 0 en el mes 3 y se queda ahi hasta el 6 (4 meses de 6).
        "government_approval": [40.0, 12.0, 0.0, 0.0, 0.0, 0.0],
        # Nunca toca ninguna cota.
        "inflation": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
    }
    found = detect_saturation(series, ranges)

    assert "inflation" not in found
    sat = found["government_approval"]
    assert sat.bound == "lo"
    assert sat.bound_value == 0.0
    assert sat.first_month == 3
    assert sat.months_at_bound == 4
    assert sat.months_run == 6
    assert sat.share_at_bound == 4 / 6


def test_detect_saturation_reports_the_bound_where_it_stays_longest() -> None:
    ranges = {"social_tension": (0.0, 100.0)}
    # Roza el 0 un mes y se queda clavada en 100 tres meses.
    series = {"social_tension": [0.0, 50.0, 100.0, 100.0, 100.0]}
    sat = detect_saturation(series, ranges)["social_tension"]
    assert sat.bound == "hi"
    assert sat.months_at_bound == 3
    assert sat.first_month == 3


def test_detect_saturation_ignores_variables_without_range() -> None:
    assert detect_saturation({"no_existe": [1.0, 1.0]}, {"otra": (0.0, 1.0)}) == {}


# --------------------------------------------------------------------------
# 3. Un escenario con fecha invalida se reporta sin tumbar la corrida.
# --------------------------------------------------------------------------


def test_invalid_start_date_is_reported_without_killing_the_run(tmp_path) -> None:
    body = (
        "label,start,months,expected\n"
        'malo,1950-01,12,"fuera del rango con series"\n'
        'bueno,2015-12,12,"escenario chico de prueba"\n'
    )
    scen = _write_scenarios(tmp_path, body)
    out = tmp_path / "run"
    payload = run_probe(
        out,
        country_id="argentina",
        seeds=2,
        scenarios_file=scen,
    )
    by_label = {s["label"]: s for s in payload["scenarios"]}

    assert by_label["malo"]["error"], "el escenario invalido tiene que quedar marcado"
    assert by_label["malo"]["seeds_run"] == 0
    # El escenario valido corrio igual.
    assert by_label["bueno"]["error"] == ""
    assert by_label["bueno"]["seeds_run"] == 2

    text = build_report(payload)
    assert "ERROR" in text
    assert "1950-01" in text


# --------------------------------------------------------------------------
# 4. Los escenarios son datos: una fila nueva es un escenario nuevo.
# --------------------------------------------------------------------------


def test_scenarios_come_from_the_csv_not_from_code(tmp_path) -> None:
    body = SMALL_CSV + 'otro,1998-01,24,"default en 2001-12"\n'
    scen = _write_scenarios(tmp_path, body)
    loaded = load_scenarios(scen)
    assert [s.label for s in loaded] == ["chico", "otro"]
    assert loaded[1] == ProbeScenario(
        label="otro", start="1998-01", months=24, expected="default en 2001-12"
    )


def test_argentina_ships_the_six_scenarios_of_the_emergence_log() -> None:
    scen = load_scenarios(scenarios_path("argentina"))
    assert [s.start for s in scen] == [
        "1983-12",
        "1991-04",
        "1998-01",
        "2003-06",
        "2015-12",
        "2019-12",
    ]
    # `expected` es texto libre y no puede estar vacio: es lo unico que
    # dice que paso de verdad (ADR 020 secc. 4).
    assert all(s.expected for s in scen)
    assert all(s.months > 0 for s in scen)


def test_missing_scenarios_file_says_so(tmp_path) -> None:
    try:
        load_scenarios(tmp_path / "no_esta.csv")
    except FileNotFoundError as exc:
        assert "probe_scenarios" in str(exc) or "no_esta.csv" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("tenia que levantar FileNotFoundError")


# --------------------------------------------------------------------------
# 5. Rango fisico: una violacion es un bug, no un resultado.
# --------------------------------------------------------------------------


def test_detect_physical_violations_flags_impossible_values() -> None:
    series = {
        "unemployment": [8.0, 9.0, 55.0, 60.0],  # > 40 %
        "real_wage": [100.0, 5.0],  # fuera de [10, 400]
        "inflation": [3.0, 4.0],  # normal
    }
    found = detect_physical_violations(series, PHYSICAL_RANGES)
    by_var = {v.variable: v for v in found}
    assert set(by_var) == {"unemployment", "real_wage"}
    assert by_var["unemployment"].month == 3
    assert by_var["unemployment"].value == 55.0
    assert by_var["real_wage"].month == 2


def test_detect_physical_violations_is_quiet_on_normal_runs() -> None:
    series = {
        "unemployment": [8.0, 9.0, 10.0],
        "real_wage": [100.0, 120.0, 90.0],
        "government_approval": [0.0, 50.0, 100.0],
    }
    assert detect_physical_violations(series, PHYSICAL_RANGES) == []


def test_physical_ranges_are_wider_than_the_country_clamps() -> None:
    """Las cotas fisicas tienen que ser MAS ANCHAS que las de
    `country.json -> ranges`: si no, la sonda marcaria como bug cada
    clampeo normal (ADR 020 secc. 2.3)."""
    from republica.calibration.initial_states import flat_initial_state
    from republica.world.countries import load_country_pack

    pack = load_country_pack(
        "argentina",
        "2015-12",
        12,
        initial_state_override=flat_initial_state("2015-12"),
    )
    for variable, (lo, hi) in PHYSICAL_RANGES.items():
        clamp_lo, clamp_hi = pack.country.ranges[variable]
        assert lo <= clamp_lo, variable
        assert hi >= clamp_hi, variable
