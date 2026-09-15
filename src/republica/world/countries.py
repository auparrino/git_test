"""Paquete de pais (ADR 011): `load_country_pack("argentina")`.

Un pais es `data/` de Aurora mas `data/countries/<id>/` superpuesto: todo
archivo que el paquete NO trae se sirve de Aurora (fallback), y todo archivo
que si trae lo reemplaza. Se implementa con una carpeta "fusionada" (symlinks,
en el scratchpad del proceso, nunca en el repo) para poder reusar
`world.config.load_country` tal cual -- sin duplicar su logica de carga de
`provinces.csv`/`parties.json`/`shocks.json`/`config_hash`.

`country.json` del paquete NO tiene el mismo esquema que el de Aurora: en vez
de un `initial_state` unico trae `initial_states` (un diccionario por fecha,
ADR 011 secc. 2, con `source`/`proxy`/`assumed` por variable). Este modulo
elige la entrada de la fecha pedida, arma un `initial_state` plano, y
construye un `country.json` efectivo (compatible con `world.config.Country`)
que escribe en la carpeta fusionada antes de llamar a `load_country`.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import DEFAULT_DATA_DIR, Country, load_country
from republica.world.regime import RegimeCalendar, build_regime_calendar

COUNTRIES_ROOT = DEFAULT_DATA_DIR / "countries"

#: Subcarpetas del paquete que NO son config de motor (historia/cronologia
#: fuente, calibracion): no se fusionan en la carpeta de `data/` efectiva.
_PACK_EXCLUDE_FROM_MERGE = {"history", "politics", "calibration"}


class CountryPackError(ValueError):
    """Error de carga de un paquete de pais (ADR 011), mensaje pensado para
    la CLI (fecha sin estado inicial, pais inexistente, etc.)."""


def country_pack_dir(country_id: str) -> Path:
    d = COUNTRIES_ROOT / country_id
    if not d.is_dir():
        available = sorted(p.name for p in COUNTRIES_ROOT.iterdir() if p.is_dir())
        raise CountryPackError(
            f"No existe el paquete de pais '{country_id}' en {d}. "
            f"Paquetes disponibles: {available or '(ninguno)'}."
        )
    return d


def _merge_into(dst: Path, src: Path, exclude: frozenset[str] = frozenset()) -> None:
    for entry in sorted(src.iterdir()):
        if entry.name in exclude:
            continue
        target = dst / entry.name
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _merge_into(target, entry)
        else:
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(entry.resolve())


def _merged_dir_for(country_id: str) -> Path:
    """Carpeta fusionada, estable por proceso (`tempfile.gettempdir()`, no el
    scratchpad de la sesion: esto es infraestructura de carga, no un
    artefacto de la tarea), reconstruida en cada llamada para reflejar
    cualquier edicion posterior del paquete o de `data/`."""
    base = Path(tempfile.gettempdir()) / "republica_country_packs" / country_id
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    return base


def _parse_start(start: str) -> tuple[int, int]:
    try:
        y, m = start.split("-")
        return int(y), int(m)
    except ValueError as exc:
        raise CountryPackError(f"--start invalido: {start!r} (formato esperado YYYY-MM).") from exc


def _select_initial_state(initial_states: dict[str, dict], start: str) -> dict[str, float]:
    entry = initial_states.get(start)
    if entry is None:
        raise CountryPackError(
            f"No hay estado inicial para la fecha '{start}'. Fechas disponibles: "
            f"{sorted(initial_states)}."
        )
    flat: dict[str, float] = {}
    for var, prov in entry.items():
        has_prov = prov.get("assumed") or "source" in prov or "proxy" in prov
        if not has_prov:
            raise CountryPackError(
                f"initial_states['{start}']['{var}'] no trae source/proxy/assumed "
                "(ADR 011 secc. 2: obligatorio por variable)."
            )
        if "value" not in prov:
            raise CountryPackError(f"initial_states['{start}']['{var}'] no trae 'value'.")
        flat[var] = prov["value"]
    return flat


def term_length_months_for(constitutions_csv: Path, start: str) -> tuple[int, bool]:
    """`(term_length_meses, reelection_allowed)` vigente en `start`
    (`politics/constitutions.csv` de Aurora... aca `<paquete>/
    constitutions.csv`, ADR 011 secc. 2/deliverable 1). Sin archivo o sin
    fila que cubra la fecha: `(48, True)`, el default de Aurora (documentado:
    no se intenta reconstruir la vigencia constitucional para paises sin
    `constitutions.csv`)."""
    if not constitutions_csv.exists():
        return 48, True
    import csv as _csv

    y, m = _parse_start(start)
    target = f"{y:04d}-{m:02d}-01"
    with constitutions_csv.open(encoding="utf-8", newline="") as fh:
        for row in _csv.DictReader(fh):
            date_from = row["date_from"]
            date_to = row["date_to"] or "9999-12-31"
            if date_from <= target <= date_to:
                years = int(float(row["term_length_years"]))
                reelection = row["reelection_allowed"].strip().lower() == "true"
                return years * 12, reelection
    return 48, True


def merged_data_dir_for_pack(
    country_id: str, start: str, months: int, regime_mode: str = "auto"
) -> Path:
    """La carpeta fusionada (`data/` de Aurora + paquete) que `load_country_pack`
    escribe, ya con un `country.json` de un solo `initial_state` (esquema de
    Aurora) para la fecha/duracion pedidas. Pensado para `republica
    experiment` (ADR 011, deliverable 1: `base: {country: ..., start: ...}`
    en el YAML de un experimento): esa carpeta es un `data_dir` valido para
    `experiments/config.py::_build_country`, overrides `country.*` de
    `arms`/`sweep` incluidos, sin duplicar la logica de resolucion de
    `country.json`."""
    load_country_pack(country_id, start, months, regime_mode)
    return Path(tempfile.gettempdir()) / "republica_country_packs" / country_id


@dataclass
class CountryPack:
    """Todo lo que `republica run --country <id>` necesita ademas del
    `Country` de siempre: rutas del paquete y datos que `world/config.py` no
    sabe cargar (calendario de regimen, coeficientes bimonetarios,
    exogenas/shocks historicos)."""

    country: Country
    pack_dir: Path
    reelection_allowed: bool
    bimonetary_coefficients: BimonetaryCoefficients
    regime_calendar: RegimeCalendar
    historical_forced_shocks: dict[int, list[str]] = field(default_factory=dict)
    historical_exogenous: dict[int, tuple[float, float]] = field(default_factory=dict)
    initial_states_coverage: dict[str, dict[str, str]] = field(default_factory=dict)


AURORA_COUNTRY_JSON_TEXT = (DEFAULT_DATA_DIR / "country.json").read_text(encoding="utf-8")


def _build_merged_dir(country_id: str) -> tuple[Path, Path, dict]:
    pack_dir = country_pack_dir(country_id)
    raw_country = json.loads((pack_dir / "country.json").read_text(encoding="utf-8"))
    merged = _merged_dir_for(country_id)
    _merge_into(merged, DEFAULT_DATA_DIR, exclude=frozenset({"countries"}))
    _merge_into(merged, pack_dir, exclude=frozenset(_PACK_EXCLUDE_FROM_MERGE))
    return pack_dir, merged, raw_country


def load_country_pack_annual(country_id: str, start_year: int, years: int) -> Country:
    """Variante de `load_country_pack` para `features.annual_mode` (ADR 011
    secc. 6, arranques anteriores a 1943): NO hay `initial_states` para esas
    fechas (`initial_states` del ADR 011 secc. 2 solo cubre 1983+, la unica
    ventana con series reales suficientes para un estado mensual completo),
    asi que se usa el `initial_state` de Aurora (el modo anual ya se declara
    "exploratorio" en cada salida, ADR 011 secc. 6: no pretende que ese
    estado inicial sea un dato real de esa fecha). El resto del paquete
    (estructura/coeficientes/shocks/regimen real por año) SI se usa."""
    pack_dir, merged, raw_country = _build_merged_dir(country_id)
    effective = dict(raw_country)
    for key in ("initial_states", "initial_states_notes", "bimonetary", "country_id", "_comment"):
        effective.pop(key, None)
    effective["name"] = raw_country.get("name", country_id)
    effective["start"] = {"year": start_year, "month": 1}
    effective["months"] = years
    effective["term_length"] = 0
    aurora_default = json.loads(AURORA_COUNTRY_JSON_TEXT)
    effective["initial_state"] = aurora_default["initial_state"]
    country_json_path = merged / "country.json"
    country_json_path.unlink(missing_ok=True)
    country_json_path.write_text(json.dumps(effective, ensure_ascii=False), encoding="utf-8")
    return load_country(merged)


def load_country_pack(
    country_id: str,
    start: str,
    months: int,
    regime_mode: str = "auto",
) -> CountryPack:
    """Carga el paquete `country_id`, elige el estado inicial de `start`
    (`YYYY-MM`) y arma un `Country` (`world.config.Country`) para correr
    `months` meses desde ahi. `regime_mode`: `"auto"` o `"democracy"` (ver
    `world/regime.py::build_regime_calendar`)."""
    pack_dir, merged, raw_country = _build_merged_dir(country_id)
    if "initial_states" not in raw_country:
        raise CountryPackError(
            f"{pack_dir / 'country.json'} no tiene 'initial_states' (ADR 011 secc. 2)."
        )
    y, m = _parse_start(start)
    flat_initial_state = _select_initial_state(raw_country["initial_states"], start)
    term_length, reelection_allowed = term_length_months_for(pack_dir / "constitutions.csv", start)

    effective_country_json = dict(raw_country)
    effective_country_json.pop("initial_states", None)
    effective_country_json.pop("initial_states_notes", None)
    effective_country_json.pop("bimonetary", None)
    effective_country_json.pop("country_id", None)
    effective_country_json.pop("_comment", None)
    effective_country_json["name"] = raw_country.get("name", country_id)
    effective_country_json["start"] = {"year": y, "month": m}
    effective_country_json["months"] = months
    effective_country_json["term_length"] = term_length
    effective_country_json["initial_state"] = flat_initial_state
    # `merged / "country.json"` es un SYMLINK al `country.json` real del
    # paquete (puesto ahi por `_merge_into` arriba): hay que sacarlo antes de
    # escribir, si no `write_text` sigue el symlink y pisa el archivo fuente
    # del paquete (¡NUNCA se debe escribir en `data/countries/<id>/`!).
    country_json_path = merged / "country.json"
    country_json_path.unlink(missing_ok=True)
    country_json_path.write_text(
        json.dumps(effective_country_json, ensure_ascii=False), encoding="utf-8"
    )

    country = load_country(merged)

    bimonetary_coeffs = BimonetaryCoefficients.from_dict(raw_country.get("bimonetary"))
    regime_calendar = build_regime_calendar(
        pack_dir / "politics" / "events.csv", y, m, months, regime_mode
    )
    historical_forced = historical_shocks_calendar(pack_dir, y, m, months)
    coverage = {
        date: {var: _provenance_kind(prov) for var, prov in entry.items()}
        for date, entry in raw_country["initial_states"].items()
    }

    return CountryPack(
        country=country,
        pack_dir=pack_dir,
        reelection_allowed=reelection_allowed,
        bimonetary_coefficients=bimonetary_coeffs,
        regime_calendar=regime_calendar,
        historical_forced_shocks=historical_forced,
        initial_states_coverage=coverage,
    )


def _provenance_kind(prov: dict) -> str:
    if prov.get("assumed"):
        return "assumed"
    if "source" in prov:
        return "source"
    if "proxy" in prov:
        return "proxy"
    return "?"


#: Shocks del calendario historico que NUNCA se fuerzan (ADR 011 secc. 4:
#: `hyperinflation_regime` es el estado endogeno de Aurora, no un shock
#: forzable -- ni siquiera esta en `shocks.json`, forzarlo tiraria
#: `KeyError` en `world/events.py::ShockCatalog.apply_month`).
NEVER_FORCED_SHOCK_IDS = frozenset({"hyperinflation_regime"})


def historical_shocks_calendar(
    pack_dir: Path, start_year: int, start_month: int, months: int
) -> dict[int, list[str]]:
    """`politics/shocks_calendar.csv` -> `forced_shocks` (ADR 011 secc. 4),
    en el mismo formato que ya acepta `engine.simulation.run(forced_shocks=)`
    -- no hace falta ningun cambio de motor para "forzar" un shock del
    calendario, solo traducir fecha -> indice de mes de esta corrida."""
    import csv as _csv

    path = pack_dir / "politics" / "shocks_calendar.csv"
    out: dict[int, list[str]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in _csv.DictReader(fh):
            shock_id = row["shock_id"]
            if shock_id in NEVER_FORCED_SHOCK_IDS:
                continue
            y, m = int(row["date"][:4]), int(row["date"][5:7])
            idx = (y - start_year) * 12 + (m - start_month) + 1
            if 1 <= idx <= months:
                out.setdefault(idx, []).append(shock_id)
    return out


def historical_exogenous_series(
    pack_dir: Path, start_year: int, start_month: int, months: int
) -> dict[int, tuple[float, float]]:
    """`{month_index: (commodity_price, world_demand)}` (ADR 011 secc. 5,
    `--historical-exogenous`): `commodity_price` de `gold_price_annual.csv`/
    `oil_price_annual.csv` (ADR: "usar gold_price_annual/oil_price_annual
    solo si no existe una serie agropecuaria" -- no hay ninguna serie de
    soja/trigo en `history/` a la fecha de A2, asi que se usa el promedio
    simple de oro y petroleo, reescalado a base 100 en el primer año de la
    corrida, como proxy declarado); `world_demand` fijo en 100 (constante:
    ADR "si no [hay PIB mundial del BM], constante 100" -- `history/` no
    trae una serie de PIB mundial)."""
    import csv as _csv

    def load_annual(name: str) -> dict[int, float]:
        p = pack_dir / "history" / f"{name}.csv"
        if not p.exists():
            return {}
        rows: dict[int, float] = {}
        with p.open(encoding="utf-8", newline="") as fh:
            for row in _csv.DictReader(fh):
                y = int(row["date"][:4])
                rows[y] = float(row["value"])
        return rows

    gold = load_annual("gold_price_annual")
    oil = load_annual("oil_price_annual")
    years = sorted(set(gold) | set(oil))
    if not years:
        return {}

    def combined(y: int) -> float | None:
        vals = [v[y] for v in (gold, oil) if y in v]
        return sum(vals) / len(vals) if vals else None

    base_year = start_year
    base = combined(base_year)
    if base is None:
        nearest_year = min(years, key=lambda yy: abs(yy - base_year))
        base = combined(nearest_year)
    if not base:
        return {}

    out: dict[int, tuple[float, float]] = {}
    last_value = 100.0
    for month_idx in range(1, months + 1):
        total_months = (start_month - 1) + (month_idx - 1)
        y = start_year + total_months // 12
        v = combined(y)
        if v is not None:
            last_value = 100.0 * v / base
        out[month_idx] = (last_value, 100.0)
    return out
