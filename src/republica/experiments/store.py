"""DuckDB de experimentos (ADR 008 secc. 3): `republica experiment load
<dir> --db simulations/republica.duckdb` crea/actualiza las 9 tablas de la
tabla de la ADR a partir de los JSONL de `<dir>` (uno por `(arm, seed)`,
escritos por `experiments/runner.py`).

`duckdb` es dependencia opcional (`[analysis]`): se importa perezosamente
DENTRO de `load_experiment`/`open_db`, nunca a nivel de modulo -- el
runner (`experiments/runner.py`) no la necesita para nada, y sin instalar
el extra estas dos funciones fallan con un mensaje en castellano en vez de
un `ImportError` crudo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from republica import __version__
from republica.engine import narrate as narrate_mod
from republica.experiments.runner import META_NAME

_MISSING_DUCKDB_MSG = (
    "duckdb no esta instalado en este entorno. Instalar el extra opcional "
    "de analisis con `uv sync --group dev --extra analysis` (o `pip install "
    "'republica-artificial[analysis]'`) para usar `experiment load`/`report`."
)


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - depende de que falte el extra
        raise RuntimeError(_MISSING_DUCKDB_MSG) from exc
    return duckdb


#: DDL de las 9 tablas de ADR secc. 3 (una clave primaria por tabla, la
#: misma columna que dice la columna "Clave" de la tabla del ADR -- asi
#: `INSERT ... ON CONFLICT (clave) DO NOTHING` es la carga idempotente que
#: pide el ADR literal).
_SCHEMA_SQL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR PRIMARY KEY,
        experiment VARCHAR,
        arm VARCHAR,
        seed INTEGER,
        outcome VARCHAR,
        months INTEGER,
        config_hash VARCHAR,
        package_version VARCHAR,
        timestamp VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS months (
        run_id VARCHAR,
        month INTEGER,
        state_json VARCHAR,
        exo_json VARCHAR,
        policy_json VARCHAR,
        aux_json VARCHAR,
        cohorts_json VARCHAR,
        events_json VARCHAR,
        PRIMARY KEY (run_id, month)
    )""",
    """CREATE TABLE IF NOT EXISTS actions (
        run_id VARCHAR,
        month INTEGER,
        seq INTEGER,
        actor VARCHAR,
        type VARCHAR,
        params_json VARCHAR,
        reason VARCHAR,
        authorized BOOLEAN,
        denied_reason VARCHAR,
        score_json VARCHAR,
        PRIMARY KEY (run_id, month, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS negotiations (
        run_id VARCHAR,
        month INTEGER,
        actor VARCHAR,
        rounds_json VARCHAR,
        result VARCHAR,
        concession_json VARCHAR,
        PRIMARY KEY (run_id, month, actor)
    )""",
    """CREATE TABLE IF NOT EXISTS votes (
        run_id VARCHAR,
        month INTEGER,
        bill VARCHAR,
        by_party_json VARCHAR,
        total DOUBLE,
        approved BOOLEAN,
        PRIMARY KEY (run_id, month, bill)
    )""",
    """CREATE TABLE IF NOT EXISTS perception (
        run_id VARCHAR,
        month INTEGER,
        cohort VARCHAR,
        perceived_json VARCHAR,
        real_json VARCHAR,
        PRIMARY KEY (run_id, month, cohort)
    )""",
    """CREATE TABLE IF NOT EXISTS elections (
        run_id VARCHAR,
        month INTEGER,
        result_json VARCHAR,
        PRIMARY KEY (run_id, month)
    )""",
    """CREATE TABLE IF NOT EXISTS traces (
        trace_id VARCHAR PRIMARY KEY,
        run_id VARCHAR,
        model VARCHAR,
        tokens_json VARCHAR,
        latency_ms DOUBLE,
        parse_error VARCHAR,
        eval_score_json VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS evals (
        report_id VARCHAR,
        metric VARCHAR,
        value DOUBLE,
        baseline DOUBLE,
        ci_json VARCHAR,
        PRIMARY KEY (report_id, metric)
    )""",
)


def open_db(db_path: str | Path):
    """Conecta (creando si no existe) y asegura el esquema de las 9 tablas."""
    duckdb = _duckdb()
    con = duckdb.connect(str(db_path))
    for stmt in _SCHEMA_SQL:
        con.execute(stmt)
    # `events_json` en `months` (hallazgo #8 de REVIEW_003, agregado despues
    # de la carga inicial de ADR 008): `CREATE TABLE IF NOT EXISTS` no toca
    # un `.duckdb` YA cargado con el esquema viejo (7 columnas) -- sin este
    # `ALTER TABLE`, `ml/regimes.py` fallaria con "column events_json does
    # not exist" sobre cualquier base cargada antes de este cambio.
    con.execute("ALTER TABLE months ADD COLUMN IF NOT EXISTS events_json VARCHAR")
    return con


def _bulk_insert(con: Any, table: str, n_cols: int, rows: list[tuple]) -> None:
    """Inserta `rows` (tuplas de `n_cols` columnas, en el mismo orden que la
    DDL de `table`) de una sola vez, en forma columnar (`unnest` por
    columna) en vez de `executemany` fila por fila.

    `con.executemany("INSERT ... ON CONFLICT ...", rows)` (la version
    obvia) resulto ~20x mas lento en la practica para tablas con `PRIMARY
    KEY` (medido cargando `central_bank_independence`: ~2 ms/fila, ~5 s
    solo para las ~1400 `actions` de UNA corrida de 48 meses -- 340
    corridas de los 3 experimentos canonicos hubieran tardado mas de media
    hora): cada llamada de `executemany` paga el viaje completo
    Python -> C++ (bind + chequeo de `PRIMARY KEY`) UNA VEZ POR FILA. La
    forma columnar arma un `SELECT` con una columna por parametro (una
    lista de Python -> un `LIST` de DuckDB, `unnest`eada) y hace el INSERT
    entero (con su chequeo de conflicto) en una sola llamada vectorizada."""
    if not rows:
        return
    columns = list(zip(*rows, strict=True))
    select = ", ".join(f"unnest(${i + 1}) AS c{i}" for i in range(n_cols))
    con.execute(
        f"INSERT INTO {table} SELECT * FROM (SELECT {select}) ON CONFLICT DO NOTHING",
        [list(c) for c in columns],
    )


def _run_id(experiment: str, arm: str, seed: int) -> str:
    return f"{experiment}:{arm}:{seed}"


def _load_one_run(con: Any, meta: dict[str, Any], arm: str, seed: int, jsonl_path: Path) -> None:
    run_id = _run_id(meta["experiment_name"], arm, seed)
    loaded = narrate_mod.load_jsonl(jsonl_path)
    arm_meta = meta["arms"].get(arm, {})

    con.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (run_id) DO NOTHING",
        [
            run_id,
            meta["experiment_name"],
            arm,
            seed,
            loaded.summary.get("outcome"),
            len(loaded.records),
            loaded.summary.get("config_hash", arm_meta.get("config_hash")),
            meta.get("package_version", __version__),
            meta.get("generated_at", ""),
        ],
    )

    months_rows = [
        (
            run_id,
            r["month_index"],
            json.dumps(r.get("state", {}), ensure_ascii=False),
            json.dumps(r.get("exo", {}), ensure_ascii=False),
            json.dumps(r.get("policy", {}), ensure_ascii=False),
            json.dumps(r.get("aux", {}), ensure_ascii=False),
            json.dumps(r.get("cohorts", {}), ensure_ascii=False),
            #: Eventos del mes (hallazgo #8 de REVIEW_003): rupturas de
            #: acuerdo (`agreement_broken:...`) viven aca, no en
            #: `negotiations.result` -- ver `ml/regimes.py::
            #: build_vectors_from_db`.
            json.dumps(r.get("events", []), ensure_ascii=False),
        )
        for r in loaded.records
    ]
    _bulk_insert(con, "months", 8, months_rows)

    action_rows = []
    for month, actions in loaded.actions_by_month.items():
        for seq, a in enumerate(actions):
            action_rows.append(
                (
                    run_id,
                    month,
                    seq,
                    a.get("actor"),
                    a.get("type"),
                    json.dumps(a.get("params") or {}, ensure_ascii=False),
                    a.get("reason"),
                    bool(a.get("authorized", True)),
                    a.get("denied_reason"),
                    json.dumps(a.get("score") or {}, ensure_ascii=False),
                )
            )
    _bulk_insert(con, "actions", 10, action_rows)

    negotiation_rows = []
    for month, negs in loaded.negotiations_by_month.items():
        for n in negs:
            negotiation_rows.append(
                (
                    run_id,
                    month,
                    n.get("actor"),
                    json.dumps(n.get("turns") or [], ensure_ascii=False),
                    n.get("outcome"),
                    json.dumps(n.get("agreement") or {}, ensure_ascii=False),
                )
            )
    _bulk_insert(con, "negotiations", 6, negotiation_rows)

    vote_rows = []
    for month, votes in loaded.votes_by_month.items():
        for v in votes:
            vote_rows.append(
                (
                    run_id,
                    month,
                    v.get("bill_id"),
                    json.dumps(v.get("parties") or [], ensure_ascii=False),
                    v.get("yes_total"),
                    bool(v.get("passed", False)),
                )
            )
    _bulk_insert(con, "votes", 6, vote_rows)

    #: `PerceptionRecord` es UNA linea por mes con `cohorts: {cohort_id:
    #: {...}}` (ADR 005 secc. 4, no una linea por cohorte); la tabla del
    #: ADR 008 secc. 3 pide clave `(run_id, month, cohort)`, asi que se
    #: expande aca: una fila de `perception` por `(mes, cohorte)`, con
    #: `real_json` (comun a todas las cohortes del mes: inflacion/desempleo
    #: reales) y `perceived_json` (lo propio de esa cohorte).
    perception_rows = []
    for month, perceptions in loaded.perceptions_by_month.items():
        for p in perceptions:
            real = {
                "real_inflation": p.get("real_inflation"),
                "real_unemployment": p.get("real_unemployment"),
                "perception_gap": p.get("perception_gap"),
                #: Influencia de cada medio ese mes (ADR 005 secc. 4.5):
                #: no tiene columna propia en la tabla `perception` del ADR
                #: 008 secc. 3 (clave `run_id, month, cohort`, sin
                #: `outlet`), asi que viaja aca -- lo usa la consulta
                #: canonica "perception_gap por medio dominante"
                #: (`experiments/queries/perception_gap_by_dominant_outlet.sql`).
                "outlet_influence": p.get("outlet_influence") or {},
            }
            for cohort_id, cohort_data in (p.get("cohorts") or {}).items():
                perception_rows.append(
                    (
                        run_id,
                        month,
                        cohort_id,
                        json.dumps(cohort_data, ensure_ascii=False),
                        json.dumps(real, ensure_ascii=False),
                    )
                )
    _bulk_insert(con, "perception", 5, perception_rows)

    election_rows = [
        (run_id, month, json.dumps(e, ensure_ascii=False))
        for month, elections in loaded.elections_by_month.items()
        for e in elections
    ]
    _bulk_insert(con, "elections", 3, election_rows)

    trace_rows = []
    for _, traces in loaded.traces_by_month.items():
        for t in traces:
            trace_id = f"{run_id}:{t.get('month', 0):03d}:{t.get('actor_id', '')}"
            trace_rows.append(
                (
                    trace_id,
                    run_id,
                    t.get("model"),
                    json.dumps(t.get("tokens") or {}, ensure_ascii=False),
                    t.get("latency_ms"),
                    t.get("parse_error"),
                    json.dumps(t.get("eval_score") or {}, ensure_ascii=False),
                )
            )
    _bulk_insert(con, "traces", 7, trace_rows)


def load_experiment(out_dir: str | Path, db_path: str | Path) -> dict[str, int]:
    """`republica experiment load <dir> --db <db_path>` (ADR secc. 3):
    carga cada JSONL de `<dir>/<arm>/<seed>.jsonl` en las tablas de
    `open_db`. Idempotente: correrlo dos veces sobre el mismo `<dir>` no
    duplica filas (`ON CONFLICT DO NOTHING` por la clave de cada tabla)."""
    out = Path(out_dir)
    meta_path = out / META_NAME
    if not meta_path.exists():
        raise FileNotFoundError(f"{out} no tiene {META_NAME} (¿se corrio 'experiment run' antes?)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    con = open_db(db_path)
    n_runs = 0
    for arm in meta["arms"]:
        arm_dir = out / arm
        if not arm_dir.exists():
            continue
        for jsonl_path in sorted(arm_dir.glob("*.jsonl")):
            seed = int(jsonl_path.stem)
            _load_one_run(con, meta, arm, seed, jsonl_path)
            n_runs += 1
    con.close()

    return {"experiment": meta["experiment_name"], "runs_seen": n_runs}


__all__ = ["load_experiment", "open_db"]
