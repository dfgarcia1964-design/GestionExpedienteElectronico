from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from legal_ui.despacho_store import (
    CASE_STATES,
    TASK_STATES,
    all_open_tasks,
    case_metrics,
    client_name,
    events_in_range,
    export_excel,
    export_json,
    find_case,
    global_metrics,
    import_excel,
    import_json,
    load_store,
    new_id,
    parse_date,
    reset_store,
    save_store,
)
from legal_ui.lexivox_sidebar import render_lexivox_sidebar
from legal_ui.lexivox_theme import FILTER_OPTIONS, LEXIVOX_CSS, STATUS_LABELS


st.set_page_config(
    page_title="Lexivox | Gestión del Despacho",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(LEXIVOX_CSS, unsafe_allow_html=True)

if "lexivox_vista" not in st.session_state:
    st.session_state.lexivox_vista = "casos"
if "despacho_store" not in st.session_state:
    st.session_state.despacho_store = load_store()
if "caso_seleccionado_id" not in st.session_state:
    st.session_state.caso_seleccionado_id = st.session_state.despacho_store["casos"][0]["id"]
if "filtro_casos" not in st.session_state:
    st.session_state.filtro_casos = "todos"
if "calendario_fecha" not in st.session_state:
    st.session_state.calendario_fecha = date.today()


def persist() -> None:
    save_store(st.session_state.despacho_store)


def filtrar_casos(casos: list[dict], query: str) -> list[dict]:
    filtro = st.session_state.filtro_casos
    rows = casos
    if filtro != "todos":
        rows = [case for case in rows if case.get("estado") == filtro]
    if query:
        rows = [
            case
            for case in rows
            if query in case.get("nombre", "").lower()
            or query in case.get("radicado", "").lower()
            or query in client_name(st.session_state.despacho_store, case.get("cliente_id", "")).lower()
        ]
    return rows


def render_metricas() -> None:
    metricas = global_metrics(st.session_state.despacho_store)
    st.markdown(
        f"""
        <div class="lx-metric-grid">
            <div class="lx-metric">
                <div class="lx-metric-label">Casos activos</div>
                <div class="lx-metric-value ok">{metricas['activos']}</div>
            </div>
            <div class="lx-metric">
                <div class="lx-metric-label">Clientes</div>
                <div class="lx-metric-value">{metricas['clientes']}</div>
            </div>
            <div class="lx-metric">
                <div class="lx-metric-label">Tareas abiertas</div>
                <div class="lx-metric-value">{metricas['tareas']}</div>
            </div>
            <div class="lx-metric">
                <div class="lx-metric-label">Vencidas</div>
                <div class="lx-metric-value warn">{metricas['vencidas']}</div>
            </div>
            <div class="lx-metric">
                <div class="lx-metric-label">Eventos 7 días</div>
                <div class="lx-metric-value">{metricas['eventos']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_persistencia() -> None:
    with st.expander("💾 Respaldo e importación (JSON / Excel)", expanded=False):
        col_json, col_xlsx, col_reset = st.columns(3)
        store = st.session_state.despacho_store

        with col_json:
            st.download_button(
                "Descargar JSON",
                data=export_json(store),
                file_name="despacho.json",
                mime="application/json",
                use_container_width=True,
            )
            uploaded_json = st.file_uploader("Importar JSON", type=["json"], key="upload_json")
            if uploaded_json and st.button("Aplicar JSON", key="apply_json"):
                st.session_state.despacho_store = import_json(uploaded_json.getvalue())
                persist()
                st.success("Datos JSON importados.")
                st.rerun()

        with col_xlsx:
            st.download_button(
                "Descargar Excel",
                data=export_excel(store),
                file_name="despacho.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            uploaded_xlsx = st.file_uploader("Importar Excel", type=["xlsx"], key="upload_xlsx")
            if uploaded_xlsx and st.button("Aplicar Excel", key="apply_xlsx"):
                st.session_state.despacho_store = import_excel(uploaded_xlsx.getvalue())
                persist()
                st.success("Datos Excel importados.")
                st.rerun()

        with col_reset:
            if st.button("Restaurar demo", use_container_width=True):
                st.session_state.despacho_store = reset_store()
                st.session_state.caso_seleccionado_id = st.session_state.despacho_store["casos"][0]["id"]
                st.success("Se restauraron los datos de ejemplo.")
                st.rerun()


def render_vista_casos(query: str) -> None:
    store = st.session_state.despacho_store
    header_col, action_col = st.columns([4, 1])
    with header_col:
        st.markdown(
            """
            <div class="lx-header">
                <div class="lx-title">Casos</div>
                <div class="lx-subtitle">
                    Gestiona asuntos, tareas, plazos, notas y tiempo del despacho.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if st.button("➕ Nuevo caso", type="primary", use_container_width=True):
            st.session_state.mostrar_formulario_caso = True

    if st.session_state.get("mostrar_formulario_caso"):
        clientes = store.get("clientes", [])
        with st.expander("Registrar nuevo caso", expanded=True):
            with st.form("nuevo_caso"):
                nombre = st.text_input("Nombre del asunto")
                cliente_id = st.selectbox(
                    "Cliente",
                    options=[client["id"] for client in clientes],
                    format_func=lambda cid: client_name(store, cid),
                ) if clientes else None
                radicado = st.text_input("Radicación")
                estado = st.selectbox("Estado", CASE_STATES, format_func=lambda k: STATUS_LABELS[k])
                notas = st.text_area("Notas iniciales")
                if st.form_submit_button("Guardar caso"):
                    if nombre.strip() and cliente_id:
                        nuevo = {
                            "id": new_id("c"),
                            "nombre": nombre.strip(),
                            "cliente_id": cliente_id,
                            "radicado": radicado.strip() or "Sin radicado",
                            "estado": estado,
                            "notas": notas.strip(),
                            "tareas": [],
                            "eventos": [],
                            "tiempo": [],
                        }
                        store["casos"].insert(0, nuevo)
                        st.session_state.caso_seleccionado_id = nuevo["id"]
                        st.session_state.mostrar_formulario_caso = False
                        persist()
                        st.rerun()
                    else:
                        st.error("Nombre y cliente son obligatorios.")

    filter_cols = st.columns(len(FILTER_OPTIONS))
    for col, (key, label) in zip(filter_cols, FILTER_OPTIONS):
        with col:
            active = st.session_state.filtro_casos == key
            if st.button(label, key=f"filtro_{key}", use_container_width=True, type="primary" if active else "secondary"):
                st.session_state.filtro_casos = key
                st.rerun()

    casos_filtrados = filtrar_casos(store.get("casos", []), query)
    if casos_filtrados and not any(case["id"] == st.session_state.caso_seleccionado_id for case in casos_filtrados):
        st.session_state.caso_seleccionado_id = casos_filtrados[0]["id"]

    lista_col, detalle_col = st.columns([1.1, 1.4])
    with lista_col:
        st.markdown('<div class="lx-panel"><div class="lx-panel-title">Listado de casos</div>', unsafe_allow_html=True)
        if not casos_filtrados:
            st.markdown('<div class="lx-empty">No hay casos con este filtro.</div>', unsafe_allow_html=True)
        else:
            opciones = {
                case["id"]: f"{case['nombre']} — {client_name(store, case.get('cliente_id', ''))}"
                for case in casos_filtrados
            }
            seleccion = st.radio(
                "Casos",
                options=list(opciones.keys()),
                format_func=lambda cid: opciones[cid],
                index=list(opciones.keys()).index(st.session_state.caso_seleccionado_id)
                if st.session_state.caso_seleccionado_id in opciones
                else 0,
                label_visibility="collapsed",
            )
            if seleccion != st.session_state.caso_seleccionado_id:
                st.session_state.caso_seleccionado_id = seleccion
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with detalle_col:
        case = find_case(store, st.session_state.caso_seleccionado_id)
        st.markdown('<div class="lx-panel"><div class="lx-panel-title">Detalle del caso</div>', unsafe_allow_html=True)
        if not case:
            st.markdown('<div class="lx-empty">Selecciona un caso para ver tareas, notas, eventos y tiempo.</div>', unsafe_allow_html=True)
        else:
            metrics = case_metrics(case)
            st.markdown(f"### {case['nombre']}")
            st.caption(f"{client_name(store, case.get('cliente_id', ''))} · Rad. {case.get('radicado', '')}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tareas abiertas", metrics["tareas_abiertas"])
            m2.metric("Vencidas", metrics["vencidas"])
            m3.metric("Eventos 7d", metrics["eventos_7d"])
            m4.metric("Sin facturar", f"{metrics['minutos_sin_facturar']} min")

            tab_tareas, tab_notas, tab_eventos, tab_tiempo = st.tabs(["Tareas", "Notas", "Eventos", "Tiempo"])
            with tab_tareas:
                if case["tareas"]:
                    st.dataframe(pd.DataFrame(case["tareas"]), use_container_width=True, hide_index=True)
                with st.form(f"nueva_tarea_{case['id']}"):
                    titulo = st.text_input("Nueva tarea")
                    vence = st.date_input("Vence", value=date.today() + timedelta(days=3))
                    estado = st.selectbox("Estado", TASK_STATES)
                    if st.form_submit_button("Agregar tarea"):
                        case["tareas"].append(
                            {
                                "id": new_id("t"),
                                "titulo": titulo.strip(),
                                "estado": estado,
                                "vence": vence.isoformat(),
                            }
                        )
                        persist()
                        st.rerun()

            with tab_notas:
                notas = st.text_area("Notas del caso", value=case.get("notas", ""), height=140)
                if st.button("Guardar notas", key=f"save_notes_{case['id']}"):
                    case["notas"] = notas
                    persist()
                    st.success("Notas guardadas.")

            with tab_eventos:
                if case["eventos"]:
                    st.dataframe(pd.DataFrame(case["eventos"]), use_container_width=True, hide_index=True)
                with st.form(f"nuevo_evento_{case['id']}"):
                    titulo = st.text_input("Evento")
                    fecha = st.date_input("Fecha", value=date.today())
                    hora = st.text_input("Hora", value="09:00")
                    if st.form_submit_button("Agregar evento"):
                        case["eventos"].append(
                            {"id": new_id("e"), "titulo": titulo.strip(), "fecha": fecha.isoformat(), "hora": hora}
                        )
                        persist()
                        st.rerun()

            with tab_tiempo:
                if case["tiempo"]:
                    st.dataframe(pd.DataFrame(case["tiempo"]), use_container_width=True, hide_index=True)
                with st.form(f"nuevo_tiempo_{case['id']}"):
                    minutos = st.number_input("Minutos", min_value=0, step=15, value=30)
                    descripcion = st.text_input("Descripción")
                    facturado = st.checkbox("Facturado")
                    if st.form_submit_button("Registrar tiempo"):
                        case["tiempo"].append(
                            {
                                "id": new_id("tm"),
                                "fecha": date.today().isoformat(),
                                "minutos": int(minutos),
                                "descripcion": descripcion.strip(),
                                "facturado": facturado,
                            }
                        )
                        persist()
                        st.rerun()

            nuevo_estado = st.selectbox(
                "Estado del caso",
                CASE_STATES,
                index=list(CASE_STATES).index(case.get("estado", "activo")),
                format_func=lambda k: STATUS_LABELS[k],
            )
            if st.button("Actualizar estado", key=f"estado_{case['id']}"):
                case["estado"] = nuevo_estado
                persist()
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def render_vista_clientes(query: str) -> None:
    store = st.session_state.despacho_store
    st.markdown(
        """
        <div class="lx-header">
            <div class="lx-title">Clientes</div>
            <div class="lx-subtitle">Administra la base de clientes vinculada a tus casos.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    clientes = store.get("clientes", [])
    if query:
        clientes = [
            client
            for client in clientes
            if query in client.get("nombre", "").lower()
            or query in client.get("documento", "").lower()
            or query in client.get("email", "").lower()
        ]

    col_list, col_form = st.columns([1.4, 1])
    with col_list:
        st.markdown('<div class="lx-panel"><div class="lx-panel-title">Directorio de clientes</div>', unsafe_allow_html=True)
        if clientes:
            rows = []
            for client in clientes:
                casos_cliente = [case for case in store.get("casos", []) if case.get("cliente_id") == client["id"]]
                rows.append(
                    {
                        "Nombre": client.get("nombre", ""),
                        "Documento": client.get("documento", ""),
                        "Email": client.get("email", ""),
                        "Teléfono": client.get("telefono", ""),
                        "Casos": len(casos_cliente),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.markdown('<div class="lx-empty">No hay clientes registrados.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_form:
        st.markdown('<div class="lx-panel"><div class="lx-panel-title">Nuevo cliente</div>', unsafe_allow_html=True)
        with st.form("nuevo_cliente"):
            nombre = st.text_input("Nombre / Razón social")
            documento = st.text_input("Documento / NIT")
            email = st.text_input("Correo")
            telefono = st.text_input("Teléfono")
            if st.form_submit_button("Guardar cliente"):
                if nombre.strip():
                    store["clientes"].append(
                        {
                            "id": new_id("cl"),
                            "nombre": nombre.strip(),
                            "documento": documento.strip(),
                            "email": email.strip(),
                            "telefono": telefono.strip(),
                        }
                    )
                    persist()
                    st.success("Cliente creado.")
                    st.rerun()
                else:
                    st.error("El nombre es obligatorio.")
        st.markdown("</div>", unsafe_allow_html=True)


def render_vista_tareas(query: str) -> None:
    st.markdown(
        """
        <div class="lx-header">
            <div class="lx-title">Tareas</div>
            <div class="lx-subtitle">Visualiza todas las tareas abiertas del despacho.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    tasks = all_open_tasks(st.session_state.despacho_store)
    if query:
        tasks = [
            task
            for task in tasks
            if query in task.get("titulo", "").lower()
            or query in task.get("caso", "").lower()
            or query in task.get("cliente", "").lower()
        ]
    st.markdown('<div class="lx-panel">', unsafe_allow_html=True)
    if tasks:
        df = pd.DataFrame(tasks)[["titulo", "estado", "vence", "caso", "cliente", "radicado"]]
        df.columns = ["Tarea", "Estado", "Vence", "Caso", "Cliente", "Radicado"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="lx-empty">No hay tareas abiertas.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_vista_calendario(query: str) -> None:
    store = st.session_state.despacho_store
    st.markdown(
        """
        <div class="lx-header">
            <div class="lx-title">Calendario</div>
            <div class="lx-subtitle">Consulta audiencias, vencimientos y eventos del despacho.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_cal, col_list = st.columns([1, 1.5])
    with col_cal:
        selected = st.date_input("Fecha seleccionada", value=st.session_state.calendario_fecha)
        st.session_state.calendario_fecha = selected
        week_start = selected - timedelta(days=selected.weekday())
        week_end = week_start + timedelta(days=6)
        st.caption(f"Semana: {week_start.isoformat()} → {week_end.isoformat()}")

    events_day = events_in_range(store, selected, selected)
    events_week = events_in_range(store, week_start, week_end)
    if query:
        events_day = [event for event in events_day if query in event.get("titulo", "").lower() or query in event.get("caso", "").lower()]
        events_week = [event for event in events_week if query in event.get("titulo", "").lower() or query in event.get("caso", "").lower()]

    with col_list:
        st.markdown('<div class="lx-panel"><div class="lx-panel-title">Eventos del día</div>', unsafe_allow_html=True)
        if events_day:
            st.dataframe(
                pd.DataFrame(events_day)[["fecha", "hora", "titulo", "caso", "cliente"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.markdown('<div class="lx-empty">Sin eventos para esta fecha.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="lx-panel"><div class="lx-panel-title">Agenda de la semana</div>', unsafe_allow_html=True)
    if events_week:
        df = pd.DataFrame(events_week)[["fecha", "hora", "titulo", "caso", "cliente"]]
        df.columns = ["Fecha", "Hora", "Evento", "Caso", "Cliente"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="lx-empty">No hay eventos programados esta semana.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    tasks_due = []
    for case in store.get("casos", []):
        for task in case.get("tareas", []):
            due = parse_date(task.get("vence", ""))
            if due and week_start <= due <= week_end and task.get("estado") != "completada":
                tasks_due.append(
                    {
                        "Vence": due.isoformat(),
                        "Tarea": task.get("titulo", ""),
                        "Caso": case.get("nombre", ""),
                        "Cliente": client_name(store, case.get("cliente_id", "")),
                    }
                )
    if tasks_due:
        st.markdown("#### Vencimientos de tareas en la semana")
        st.dataframe(pd.DataFrame(tasks_due), use_container_width=True, hide_index=True)


with st.sidebar:
    query = render_lexivox_sidebar(st.session_state.lexivox_vista)

render_metricas()
render_persistencia()

vista = st.session_state.lexivox_vista
if vista == "casos":
    render_vista_casos(query)
elif vista == "clientes":
    render_vista_clientes(query)
elif vista == "tareas":
    render_vista_tareas(query)
else:
    render_vista_calendario(query)
