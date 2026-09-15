"""Carga y resuelve `experiments/*.yaml` (ADR 008 secc. 1): definicion
declarativa de un experimento -- una linea base (`base`), brazos (`arms`)
como overrides sobre `country.json`/`governance.yaml`/`brains`/`features`,
un `sweep` opcional (producto cartesiano) y la lista de `seeds`/`metrics`.

Formato del override (deliverable 1, "arms son overrides (dot-path) sobre
country.json, governance.yaml, brains.yaml y features"): cada clave de
`arms.<nombre>`/`sweep` empieza por uno de 4 namespaces --
`country.<dot-path dentro del country.json crudo>`,
`governance.<actor_id>.<campo>` (mismo formato que `--governance-override`,
ADR 007 secc. 6), `brains.default` / `brains.actors.<actor_id>`, o
`features.<nombre>`. En `arms` se escriben como un YAML anidado (mas
natural: `{governance: {central_bank: {autonomy: 2}}}`); en `sweep` como
una clave plana con puntos (`country.coefficients.c_f`, literal del ADR).
`_flatten_overrides` convierte la forma anidada a la forma plana antes de
aplicar overrides, asi ambas notaciones terminan en el mismo mecanismo."""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from republica.ai.brains import DEFAULT_BRAINS_PATH, load_brains_config
from republica.world.config import (
    DEFAULT_DATA_DIR,
    Coefficients,
    Country,
    ExogenousProcess,
    Structure,
    TaylorParams,
    Terminal,
    _coalition_seats,
    _compute_config_hash,
    _load_parties,
    _load_provinces,
)
from republica.world.state import Exogenous, Policy, WorldState

#: Features default de una `Country` sin `features` en `country.json` (ADR
#: 005/006, mismo default que `world/config.py::load_country`).
_DEFAULT_FEATURES: dict[str, bool] = {
    "actors": True,
    "congress": True,
    "negotiation": True,
    "cohorts": True,
    "media": True,
    "memory": True,
    "elections": True,
}

_NAMESPACES = ("country", "governance", "brains", "features")


def _flatten_overrides(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """`{"governance": {"central_bank": {"autonomy": 2}}}` ->
    `{"governance.central_bank.autonomy": 2}` (forma anidada de `arms` a
    forma plana de dot-path, la misma que ya usa `sweep`)."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_overrides(v, key))
        else:
            out[key] = v
    return out


def _set_dot_path(d: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = d
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _fmt_value(v: Any) -> str:
    """Representacion corta de un valor de override para el nombre
    deterministico de un brazo con `sweep` (ver `resolve_arms`)."""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _group_by_namespace(dotted: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {ns: {} for ns in _NAMESPACES}
    for key, value in dotted.items():
        ns, sep, rest = key.partition(".")
        if ns not in _NAMESPACES or not sep or not rest:
            raise ValueError(
                f"override de experimento mal formado: {key!r} "
                f"(usar {'.'.join(_NAMESPACES)}.<resto> con al menos una sub-clave)"
            )
        groups[ns][rest] = value
    return groups


@dataclass(frozen=True)
class SeedsSpec:
    start: int = 0
    count: int = 1

    @property
    def values(self) -> list[int]:
        return list(range(self.start, self.start + self.count))


@dataclass(frozen=True)
class Arm:
    """Un brazo ya resuelto: todo lo que `experiments/runner.py` necesita
    para correr `engine.simulation.run()` una vez por semilla."""

    name: str
    #: Overrides aplicados (dot-path -> valor), para `runs.meta.json` y para
    #: que el reporte de `fiscal_rule` pueda reconstruir la grilla del
    #: `sweep` sin volver a parsear el nombre del brazo.
    overrides: dict[str, Any]
    #: Subconjunto de `overrides` que vino de `sweep` (vacio si el
    #: experimento no tiene `sweep`), en el mismo orden que las claves de
    #: `sweep:` del YAML.
    sweep_point: dict[str, Any]
    months: int
    country: Country
    features: dict[str, bool]
    brain_default: str
    brain_map: dict[str, str]
    #: `{"central_bank.autonomy": "4"}` (mismo formato que
    #: `run(governance_overrides=...)`, ADR 007 secc. 6 deliverable 6).
    governance_overrides: dict[str, str]
    config_hash: str


def _build_country(data_dir: Path, country_overrides: dict[str, Any]) -> tuple[Country, str]:
    """Construye una `Country` igual que `world.config.load_country`, pero
    aplicando `country_overrides` (dot-path SIN el prefijo `country.`, p.ej.
    `coefficients.c_f`) sobre el `dict` crudo de `country.json` antes de
    tipar. Devuelve `(Country, base_hash)`: `base_hash` es el
    `config_hash` de los archivos de datos en disco, SIN el override (el
    `config_hash` final de cada brazo lo computa `_arm_config_hash`,
    combinando este hash con los 4 namespaces de overrides -- asi un brazo
    sin overrides tiene el mismo `config_hash` que `load_country()`, y uno
    con overrides tiene uno distinto, reproducible)."""
    country_path = data_dir / "country.json"
    raw: dict[str, Any] = json.loads(country_path.read_text(encoding="utf-8"))
    base_hash = _compute_config_hash(data_dir)
    for dotted, value in country_overrides.items():
        _set_dot_path(raw, dotted, value)

    provinces = _load_provinces(data_dir / "provinces.csv")
    parties = _load_parties(data_dir / "parties.json")
    shocks = json.loads((data_dir / "shocks.json").read_text(encoding="utf-8"))
    country = Country(
        name=raw["name"],
        start=raw["start"],
        months=raw["months"],
        term_length=raw.get("term_length", 48),
        initial_state=WorldState.model_validate(raw["initial_state"]),
        exogenous=Exogenous.model_validate(raw["exogenous"]),
        structure=Structure.model_validate(raw["structure"]),
        exogenous_process=ExogenousProcess.model_validate(raw["exogenous_process"]),
        taylor=TaylorParams.model_validate(raw["taylor"]),
        coefficients=Coefficients.model_validate(raw["coefficients"]),
        default_policy=Policy.model_validate(raw["default_policy"]),
        policy_ranges={k: tuple(v) for k, v in raw["policy_ranges"].items()},
        ranges={k: tuple(v) for k, v in raw["ranges"].items()},
        terminal=Terminal.model_validate(raw["terminal"]),
        provinces=provinces,
        parties=parties,
        coalition_seats=_coalition_seats(parties),
        shocks=shocks,
        config_hash=base_hash,
        features=raw.get("features", dict(_DEFAULT_FEATURES)),
    )
    return country, base_hash


def _arm_config_hash(base_hash: str, overrides: dict[str, Any]) -> str:
    """`config_hash` de un brazo (ADR secc. 1: "un experimento es
    reproducible por (yaml, config_hash de cada archivo de datos, version
    del paquete)"): combina el hash de los archivos de datos en disco con
    los overrides del brazo, asi dos brazos con los mismos archivos pero
    distinto override NUNCA colisionan (deliverable 5/6 del DoD, ADR secc.
    7 punto 6)."""
    payload = json.dumps({"base": base_hash, "overrides": overrides}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_brains_spec(spec: str, data_dir: Path) -> tuple[str, dict[str, str]]:
    """`base.brains` (ADR secc. 1: `"rules"  # o data/brains.yaml`): si
    parece una ruta a un YAML (tiene `/` o termina en `.yaml`/`.yml`) se
    carga con `load_brains_config`; si no, es un spec de cerebro (`"rules"`,
    `"fake:rules"`, `"llm:ollama:<modelo>"`) que se usa como default para
    todo actor."""
    looks_like_path = "/" in spec or spec.endswith((".yaml", ".yml"))
    if looks_like_path:
        path = Path(spec)
        if not path.is_absolute():
            path = data_dir.parent / spec if (data_dir.parent / spec).exists() else path
        cfg = load_brains_config(path)
        return cfg.default, dict(cfg.actors)
    return spec, {}


@dataclass
class ExperimentConfig:
    name: str
    description: str
    base: dict[str, Any]
    seeds: SeedsSpec
    arms_raw: dict[str, dict[str, Any]]
    sweep: dict[str, list[Any]]
    metrics: list[str]
    source_path: Path
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)

    @classmethod
    def load(cls, path: str | Path, data_dir: Path | None = None) -> ExperimentConfig:
        p = Path(path)
        raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        seeds_raw = raw.get("seeds") or {"start": 0, "count": 1}
        if "name" not in raw:
            raise ValueError(f"{p}: falta 'name'")
        base = dict(raw.get("base") or {})
        # `base.country`/`base.start` (ADR 011, deliverable 7): un paquete de
        # pais en vez de Aurora. `data_dir` pasa a ser la carpeta fusionada
        # de `world.countries.load_country_pack` (mismo esquema de
        # `country.json` que Aurora, asi que `_build_country`/los overrides
        # `country.*` de `arms`/`sweep` funcionan sin ningun cambio mas).
        if data_dir is None and base.get("country"):
            from republica.world.countries import (
                CountryPackError,
                merged_data_dir_for_pack,
            )

            if not base.get("start"):
                raise ValueError(f"{p}: 'base.country' requiere 'base.start' (YYYY-MM).")
            try:
                data_dir = merged_data_dir_for_pack(
                    str(base["country"]),
                    str(base["start"]),
                    int(base.get("months") or 48),
                    str(base.get("regime_mode", "auto")),
                )
            except CountryPackError as exc:
                raise ValueError(f"{p}: {exc}") from exc
        return cls(
            name=str(raw["name"]),
            description=str(raw.get("description", "")),
            base=base,
            seeds=SeedsSpec(
                start=int(seeds_raw.get("start", 0)), count=int(seeds_raw.get("count", 1))
            ),
            arms_raw={k: dict(v or {}) for k, v in (raw.get("arms") or {}).items()},
            sweep=dict(raw.get("sweep") or {}),
            metrics=list(raw.get("metrics") or []),
            source_path=p.resolve(),
            data_dir=Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR,
        )

    def resolve_arms(self) -> list[Arm]:
        """Devuelve la lista de brazos resueltos (deliverable 1: overrides
        aplicados + `config_hash`). Con `sweep`, cada `arms.<nombre>` se
        multiplica por el producto cartesiano de `sweep` (deliverable "2x2
        -> 4 brazos con nombres deterministas"): el nombre de cada
        combinacion es `<arm>__<clave1>=<valor1>__<clave2>=<valor2>...`, en
        el mismo orden en que aparecen las claves de `sweep:` en el YAML
        (`dict` preserva orden de insercion, determinista desde `yaml.safe_load`)."""
        d = self.data_dir
        months = int(self.base.get("months") or 0) or None
        base_features_overrides = dict(self.base.get("features") or {})
        base_brains_spec = self.base.get("brains", "rules")
        base_brain_default, base_brain_map = _resolve_brains_spec(str(base_brains_spec), d)

        sweep_keys = list(self.sweep.keys())
        if sweep_keys:
            combos = [
                dict(zip(sweep_keys, values, strict=True))
                for values in itertools.product(*(self.sweep[k] for k in sweep_keys))
            ]
        else:
            combos = [{}]

        arms_raw = self.arms_raw or {"base": {}}

        arms: list[Arm] = []
        for arm_name, arm_overrides_nested in arms_raw.items():
            arm_flat = _flatten_overrides(arm_overrides_nested)
            for combo in combos:
                full_name = arm_name
                if combo:
                    suffix = "__".join(
                        f"{k.rsplit('.', 1)[-1]}={_fmt_value(v)}" for k, v in combo.items()
                    )
                    full_name = f"{arm_name}__{suffix}"
                merged = {**arm_flat, **combo}
                groups = _group_by_namespace(merged)

                country, base_hash = _build_country(d, groups["country"])
                final_hash = _arm_config_hash(base_hash, merged)
                country = country.model_copy(update={"config_hash": final_hash})

                brain_default = base_brain_default
                brain_map = dict(base_brain_map)
                for key, value in groups["brains"].items():
                    if key == "default":
                        brain_default = str(value)
                    elif key.startswith("actors."):
                        actor_id = key.split(".", 1)[1]
                        brain_map[actor_id] = str(value)
                    else:
                        raise ValueError(
                            f"override de brains desconocido: 'brains.{key}' "
                            "(usar brains.default o brains.actors.<actor_id>)"
                        )

                governance_overrides = {k: str(v) for k, v in groups["governance"].items()}

                features = dict(_DEFAULT_FEATURES)
                features.update(country.features or {})
                features.update(base_features_overrides)
                features.update(groups["features"])
                actors_on = bool(features.get("actors", True))
                cohorts_on = bool(features.get("cohorts", True))
                effective_features = {
                    "actors": actors_on,
                    "congress": bool(features.get("congress", True)) and actors_on,
                    "negotiation": bool(features.get("negotiation", True)) and actors_on,
                    "cohorts": cohorts_on,
                    "media": bool(features.get("media", True)) and actors_on and cohorts_on,
                    "memory": bool(features.get("memory", True)) and actors_on,
                    "elections": bool(features.get("elections", True)) and actors_on and cohorts_on,
                }

                arms.append(
                    Arm(
                        name=full_name,
                        overrides=merged,
                        sweep_point=combo,
                        months=months or country.months,
                        country=country,
                        features=effective_features,
                        brain_default=brain_default,
                        brain_map=brain_map,
                        governance_overrides=governance_overrides,
                        config_hash=final_hash,
                    )
                )
        return arms


__all__ = ["Arm", "ExperimentConfig", "SeedsSpec", "DEFAULT_BRAINS_PATH"]
