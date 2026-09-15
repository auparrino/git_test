"""UI Streamlit (ADR 009 secc. 7): `republica ui` la lanza con `streamlit
run`. Lee JSONL/DuckDB y llama a `Game` (`engine/game.py`) para el modo
jugable -- no duplica logica de motor, solo la muestra. El visor HTML
autocontenido (`republica viewer`) sigue existiendo aparte para compartir
una corrida sin instalar nada (ADR secc. 7, ultimo punto).

12 pestanas (ADR original secc. 23, literal): Mundo, Politica, Economia,
Congreso, Actores, Relaciones, Medios, Eventos, Trazas IA, Evals,
Experimentos, Regimenes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from republica.actors.sheet import load_actors
from republica.engine import narrate as narrate_mod
from republica.engine.dilemmas import render_text
from republica.engine.game import CAPPED_INSTRUMENTS, Game
from republica.engine.narrate import KEY_INDICATORS, annualized_inflation
from republica.engine.simulation import run as run_simulation

st.set_page_config(page_title="Republica Artificial", layout="wide")

TAB_NAMES: tuple[str, ...] = (
    "Mundo",
    "Politica",
    "Economia",
    "Congreso",
    "Actores",
    "Relaciones",
    "Medios",
    "Eventos",
    "Trazas IA",
    "Evals",
    "Experimentos",
    "Regimenes",
)


@st.cache_data(show_spinner="Corriendo una simulacion de ejemplo...")
def _sample_run_text(seed: int, months: int) -> str:
    """Corrida de ejemplo generada en memoria (ADR secc. 7, DoD "la app
    carga una corrida de ejemplo"): sin depender de un archivo en disco, la
    UI funciona apenas se instala el extra `[ui]`."""
    history = run_simulation(
        seed=seed,
        months=months,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    return history.to_jsonl()


def _load_source() -> narrate_mod.Loaded | None:
    """Fuente de datos activa (ADR secc. 7: "lee JSONL/DuckDB"): un archivo
    subido, una ruta tipeada, o la corrida de ejemplo por default."""
    st.sidebar.header("Corrida")
    mode = st.sidebar.radio("Fuente", ["Corrida de ejemplo", "Archivo .jsonl"], key="source_mode")
    if mode == "Archivo .jsonl":
        path_str = st.sidebar.text_input("Ruta al .jsonl", key="jsonl_path")
        if path_str:
            p = Path(path_str)
            if p.exists():
                try:
                    return narrate_mod.load_jsonl(p)
                except (ValueError, json.JSONDecodeError) as exc:
                    st.sidebar.error(f"No se pudo leer {p}: {exc}")
                    return None
            st.sidebar.warning(f"{p} no existe.")
        return None

    seed = st.sidebar.number_input("Semilla", min_value=0, value=0, step=1, key="sample_seed")
    months = st.sidebar.slider("Meses", min_value=3, max_value=48, value=12, key="sample_months")
    text = _sample_run_text(int(seed), int(months))
    return narrate_mod.loads_jsonl(text)


def _tab_mundo(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Indicadores")
    records = loaded.records
    if not records:
        st.info("Sin meses cargados.")
        return
    rows = [
        {"mes": r["month_index"], **{label: r["state"][key] for key, label, _ in KEY_INDICATORS}}
        for r in records
    ]
    st.line_chart(
        {label: [row[label] for row in rows] for _, label, _ in KEY_INDICATORS},
    )
    last = records[-1]
    cols = st.columns(4)
    cols[0].metric("Outcome", loaded.summary.get("outcome", "?"))
    cols[1].metric("Inflacion anual", f"{annualized_inflation(last['state']['inflation']):.1f} %")
    cols[2].metric("Aprobacion", f"{last['state']['government_approval']:.1f}")
    cols[3].metric("Estabilidad", f"{last['state']['political_stability']:.1f}")
    st.dataframe(rows, hide_index=True)


def _tab_politica(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Aprobacion, estabilidad y congreso")
    rows = loaded.records
    if rows:
        st.line_chart(
            {
                "aprobacion": [r["state"]["government_approval"] for r in rows],
                "estabilidad": [r["state"]["political_stability"] for r in rows],
                "congress_support": [r["state"]["congress_support"] for r in rows],
                "protesta": [r["state"]["protest_level"] for r in rows],
            }
        )
    st.subheader("Politica vigente (ultimo mes)")
    if rows:
        st.json(rows[-1].get("policy", {}))


def _tab_economia(loaded: narrate_mod.Loaded) -> None:
    st.subheader("PIB, inflacion, desempleo")
    rows = loaded.records
    if rows:
        st.line_chart(
            {
                "gdp_growth": [r["state"]["gdp_growth"] for r in rows],
                "inflation": [r["state"]["inflation"] for r in rows],
                "unemployment": [r["state"]["unemployment"] for r in rows],
                "reserves": [r["state"]["reserves"] for r in rows],
            }
        )


def _tab_congreso(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Votaciones")
    all_votes = [v for votes in loaded.votes_by_month.values() for v in votes]
    if not all_votes:
        st.info("Sin votaciones en esta corrida (features.congress apagado, o ninguna ley votada).")
        return
    st.dataframe(
        [
            {
                "mes": v["month"],
                "ley": v.get("bill_id"),
                "si": v.get("yes_total"),
                "umbral": v.get("threshold"),
                "aprobada": v.get("passed"),
            }
            for v in all_votes
        ],
        hide_index=True,
    )


def _tab_actores(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Fichas")
    actors = load_actors()
    st.dataframe(
        [
            {
                "id": a.id,
                "nombre": a.name,
                "rol": a.role,
                "provincia": a.province,
                "partido": a.party,
            }
            for a in actors.values()
        ],
        hide_index=True,
    )
    st.subheader("Acciones recientes")
    last_month = loaded.records[-1]["month_index"] if loaded.records else None
    if last_month is not None:
        actions = loaded.actions_by_month.get(last_month, [])
        st.dataframe(
            [
                {
                    "actor": a["actor"],
                    "tipo": a["type"],
                    "autorizada": a["authorized"],
                    "razon": a["reason"],
                }
                for a in actions
            ],
            hide_index=True,
        )


def _tab_relaciones(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Relaciones con el presidente (ficha estatica)")
    actors = load_actors()
    matrix = {a.id: a.relationship("president") for a in actors.values() if a.role != "president"}
    try:
        import networkx as nx  # noqa: PLC0415

        graph = nx.Graph()
        graph.add_node("president")
        for actor_id, rel in matrix.items():
            graph.add_node(actor_id)
            graph.add_edge("president", actor_id, weight=rel)
        st.caption(f"Grafo con {graph.number_of_nodes()} nodos (networkx disponible).")
    except ImportError:
        st.caption("networkx no instalado: se muestra la matriz.")
    st.dataframe(
        [{"actor": k, "relacion_con_presidente": v} for k, v in sorted(matrix.items())],
        hide_index=True,
    )


def _tab_medios(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Coberturas")
    last_month = loaded.records[-1]["month_index"] if loaded.records else None
    stories = []
    for actions in loaded.actions_by_month.values():
        stories.extend(a for a in actions if a["type"] == "PUBLISH_STORY")
    if not stories:
        st.info("Sin coberturas (features.media apagado, o ningun medio publico).")
        return
    st.dataframe(
        [
            {"mes": s["month"], "medio": s["actor"], "frame": s["params"].get("frame")}
            for s in stories
        ],
        hide_index=True,
    )
    st.caption(f"Ultimo mes cargado: {last_month}")


def _tab_eventos(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Shocks y eventos")
    rows = [
        {
            "mes": r["month_index"],
            "shocks_nuevos": ", ".join(r["shocks_new"]),
            "eventos": ", ".join(r["events"]),
        }
        for r in loaded.records
        if r["shocks_new"] or r["events"]
    ]
    if not rows:
        st.info("Sin eventos en esta corrida.")
        return
    st.dataframe(rows, hide_index=True)


def _tab_trazas(loaded: narrate_mod.Loaded) -> None:
    st.subheader("Trazas de decision IA (ADR 004 secc. 6)")
    all_traces = [t for traces in loaded.traces_by_month.values() for t in traces]
    if not all_traces:
        st.info("Sin trazas: esta corrida usa `brain = rules` para todos los actores.")
        return
    st.dataframe(
        [
            {
                "mes": t["month"],
                "actor": t["actor_id"],
                "modelo": t.get("model"),
                "parse_error": t.get("parse_error"),
            }
            for t in all_traces
        ],
        hide_index=True,
    )


def _tab_evals() -> None:
    st.subheader("Reportes de evals (ADR 007)")
    reports_dir = Path("evals/reports")
    if not reports_dir.exists():
        st.info(f"No hay reportes en {reports_dir}.")
        return
    reports = sorted(reports_dir.glob("*/report.json"))
    if not reports:
        st.info("Sin reportes de evals todavia.")
        return
    chosen = st.selectbox("Reporte", reports, format_func=lambda p: p.parent.name)
    st.json(json.loads(chosen.read_text(encoding="utf-8")))


def _tab_experimentos() -> None:
    st.subheader("Experimentos (ADR 008)")
    exp_dir = Path("experiments/results")
    if not exp_dir.exists():
        st.info(f"No hay resultados en {exp_dir}.")
        return
    reports = sorted(exp_dir.glob("*/report.md"))
    if not reports:
        st.info("Sin `report.md` todavia (correr `republica experiment report`).")
        return
    chosen = st.selectbox("Experimento", reports, format_func=lambda p: p.parent.name)
    st.markdown(chosen.read_text(encoding="utf-8"))


def _tab_regimenes() -> None:
    st.subheader("Regimenes (ADR 009 secc. 6)")
    db_path = st.text_input(
        "Archivo DuckDB", value="", placeholder="simulations/republica.duckdb", key="regimes_db"
    )
    if not db_path or not Path(db_path).exists():
        st.info(
            "Indica un archivo DuckDB ya cargado (`republica experiment load` + "
            "`republica ml regimes --db ...`)."
        )
        return
    try:
        from republica.experiments.store import open_db
        from republica.ml.regimes import REGIMES_TABLE_SQL
    except ImportError:
        st.error("Falta el extra `analysis` (duckdb) o `ml` (sklearn).")
        return
    con = open_db(db_path)
    con.execute(REGIMES_TABLE_SQL)
    rows = con.execute("SELECT run_id, cluster, pc1, pc2 FROM regimes ORDER BY cluster").fetchall()
    con.close()
    if not rows:
        st.info("La tabla `regimes` esta vacia (correr `republica ml regimes --db ...`).")
        return
    st.dataframe(
        [{"run_id": r, "cluster": c, "pc1": p1, "pc2": p2} for r, c, p1, p2 in rows],
        hide_index=True,
    )
    st.scatter_chart(
        {"pc1": [r[2] for r in rows], "pc2": [r[3] for r in rows], "cluster": [r[1] for r in rows]},
        x="pc1",
        y="pc2",
        color="cluster",
    )


def _play_mode() -> None:
    """Modo jugable (ADR secc. 7): mismo `Game` que la CLI. Dilemas como
    tarjetas, instrumentos como sliders con los mismos topes mensuales
    (`CAPPED_INSTRUMENTS`), estado en `st.session_state`, guardado con
    `Game.save`."""
    st.header("Modo jugable")
    if "game" not in st.session_state:
        seed = st.number_input("Semilla", min_value=0, value=1, key="play_seed")
        months = st.slider("Meses", min_value=3, max_value=48, value=12, key="play_months")
        if not st.button("Nueva partida", key="new_game"):
            return
        # No hay `return` aca a proposito: crear la partida y renderizar el
        # resto (dilemas/instrumentos/"Avanzar mes") en la MISMA corrida del
        # script deja la transicion instantanea -- volver a esperar otra
        # interaccion del usuario solo para mostrar el primer mes jugable
        # es la UX que `AppTest` (ADR secc. 7, DoD "avanza un mes en modo
        # jugable") ejercita justo: crear + avanzar en dos pasos, no tres.
        st.session_state.game = Game.new(seed=int(seed), months=int(months), actors_enabled=True)

    game: Game = st.session_state.game
    st.caption(f"Mes {game.sim.month} de {game.country.months} -- semilla {game.seed}")

    choices: dict[str, str] = {}
    if game.pending_dilemmas:
        st.subheader("Dilemas")
        for dilemma in game.pending_dilemmas:
            with st.container(border=True):
                st.markdown(f"**{dilemma.title}**")
                st.write(render_text(dilemma.text, {}))
                labels = [o.label for o in dilemma.options]
                keys = [o.key for o in dilemma.options]
                choice_idx = st.radio(
                    "Opcion",
                    range(len(labels)),
                    format_func=lambda i, _labels=labels: _labels[i],
                    key=f"dilemma_{dilemma.id}_{game.sim.month}",
                )
                choices[dilemma.id] = keys[choice_idx]

    st.subheader("Instrumentos")
    edits: dict[str, float] = {}
    cols = st.columns(len(CAPPED_INSTRUMENTS))
    for col, (instrument, cap) in zip(cols, CAPPED_INSTRUMENTS.items(), strict=True):
        current = getattr(game.policy, instrument)
        with col:
            new_value = st.slider(
                instrument,
                min_value=current - cap,
                max_value=current + cap,
                value=current,
                key=f"instr_{instrument}_{game.sim.month}",
            )
        if abs(new_value - current) > 1e-9:
            edits[instrument] = new_value

    if st.button("Avanzar mes", key="advance_month") and game.sim.outcome is None:
        game.step(choices, edits)
        st.rerun()

    if game.sim.records:
        last = game.sim.records[-1].state
        cols2 = st.columns(4)
        cols2[0].metric("Aprobacion", f"{last['government_approval']:.1f}")
        cols2[1].metric("Inflacion", f"{last['inflation']:.2f}")
        cols2[2].metric("Desempleo", f"{last['unemployment']:.1f}")
        cols2[3].metric("Estabilidad", f"{last['political_stability']:.1f}")

    if game.sim.outcome is not None:
        st.success(f"Partida terminada: {game.sim.outcome}")


def main() -> None:
    st.title("Republica Artificial")
    play_mode = st.sidebar.checkbox("Modo jugable", key="play_mode_toggle")
    if play_mode:
        _play_mode()
        st.divider()

    loaded = _load_source()
    tabs = st.tabs(list(TAB_NAMES))
    if loaded is None:
        with tabs[0]:
            st.info("Elegi una corrida en la barra lateral.")
        return

    renderers: dict[str, Any] = {
        "Mundo": lambda: _tab_mundo(loaded),
        "Politica": lambda: _tab_politica(loaded),
        "Economia": lambda: _tab_economia(loaded),
        "Congreso": lambda: _tab_congreso(loaded),
        "Actores": lambda: _tab_actores(loaded),
        "Relaciones": lambda: _tab_relaciones(loaded),
        "Medios": lambda: _tab_medios(loaded),
        "Eventos": lambda: _tab_eventos(loaded),
        "Trazas IA": lambda: _tab_trazas(loaded),
        "Evals": _tab_evals,
        "Experimentos": _tab_experimentos,
        "Regimenes": _tab_regimenes,
    }
    for tab, name in zip(tabs, TAB_NAMES, strict=True):
        with tab:
            renderers[name]()


main()
