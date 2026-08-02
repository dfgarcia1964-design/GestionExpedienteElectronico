from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pandas as pd
import streamlit as st

from legal_ui.lexivox_theme import FILTER_OPTIONS, LEXIVOX_CSS, STATUS_LABELS


st.set_page_config(
    page_title="Casos | Gestión del Despacho",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(LEXIVOX_CSS, unsafe_allow_html=True)


def _seed_cases() -> list[dict]:
    today = date.today()
    return [
        {
            "id": "c1",
            "nombre": "Vigilancia judicial — Juzgado 1 Civil",
            "cliente": "María López",
            "radicado": "2024-00123",
            "estado": "activo",
            "tareas_abiertas": 3,
            "vencidas": 1,
            "eventos_7d": 2,
            "minutos_sin_facturar": 120,
            "notas": "Falta memorial de impulso y constancia de radicación.",
            "proximo_evento": (today + timedelta(days=2)).isoformat(),
        },
        {
            "id": "c2",
            "nombre": "Tutela derecho de petición — EPS",
            "cliente": "Carlos Ruiz",
            "radicado": "2025-00456",
            "estado": "activo",
            "tareas_abiertas": 2,
            "vencidas": 0,
            "eventos_7d": 1,
            "minutos_sin_facturar": 45,
            "notas": "Esperando respuesta de la accionada.",
            "proximo_evento": (today + timedelta(days=5)).isoformat(),
        },
        {
            "id": "c3",
            "nombre": "Conciliación extrajudicial laboral",
            "cliente": "Empresa ABC S.A.S.",
            "radicado": "2023-00987",
            "estado": "pausado",
            "tareas_abiertas": 1,
            "vencidas": 0,
            "eventos_7d": 0,
            "minutos_sin_facturar": 0,
            "notas": "Pausado a solicitud del cliente.",
            "proximo_evento": "",
        },
        {
            "id": "c4",
            "nombre": "Incidente de desacato tutela",
            "cliente": "Ana Torres",
            "radicado": "2022-00321",
            "estado": "cerrado",
            "tareas_abiertas": 0,
            "vencidas": 0,
            "eventos_7d": 0,
            "minutos_sin_facturar": 0,
            "notas": "Fallo favorable. Archivo listo.",
            "proximo_evento": "",
        },
    ]


if "casos_despacho" not in st.session_state:
    st.session_state.casos_despacho = _seed_cases()

if "caso_seleccionado_id" not in st.session_state:
    st.session_state.caso_seleccionado_id = st.session_state.casos_despacho[0]["id"]

if "filtro_casos" not in st.session_state:
    st.session_state.filtro_casos = "todos"


def _filtrar_casos(casos: list[dict]) -> list[dict]:
    filtro = st.session_state.filtro_casos
    if filtro == "todos":
        return casos
    return [c for c in casos if c["estado"] == filtro]


def _metricas(casos: list[dict]) -> dict[str, int]:
    activos = [c for c in casos if c["estado"] == "activo"]
    return {
        "activos": len(activos),
        "tareas": sum(c["tareas_abiertas"] for c in casos),
        "vencidas": sum(c["vencidas"] for c in casos),
        "eventos": sum(c["eventos_7d"] for c in casos),
        "sin_facturar": sum(c["minutos_sin_facturar"] for c in casos),
    }


with st.sidebar:
    st.markdown('<div class="lx-brand">Lexivox</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="lx-brand-sub">Gestión de expedientes judiciales</div>',
        unsafe_allow_html=True,
    )
    st.text_input("Buscar casos", placeholder="Radicado, cliente, asunto...", label_visibility="collapsed")

    st.markdown('<div class="lx-nav-section">PRINCIPAL</div>', unsafe_allow_html=True)
    nav_items = [
        ("🏠 Inicio", "🏠_Inicio.py", False),
        ("🤖 Asistente Legal", "pages/2_🤖_Experto_en_Expediente_Electronico.py", False),
        ("📁 Casos", "pages/25_Gestion_Casos_Despacho.py", True),
        ("👥 Clientes", None, False),
        ("✅ Tareas", None, False),
        ("📅 Calendario", "pages/14_Control_Terminos.py", False),
        ("⚙️ Configuración", None, False),
    ]
    for label, target, active in nav_items:
        css_class = "lx-nav-item active" if active else "lx-nav-item"
        st.markdown(f'<div class="{css_class}">{label}</div>', unsafe_allow_html=True)
        if target and not active:
            try:
                st.page_link(target, label=f"Ir a {label.split(' ', 1)[1]}", use_container_width=True)
            except Exception:
                pass

    st.markdown('<div class="lx-nav-section">HERRAMIENTAS</div>', unsafe_allow_html=True)
    tool_links = [
        ("📚 Organizador Vigilancia", "pages/24_Organizador_Automatico_Vigilancia.py"),
        ("⚖️ Auditor Jurídico V2", "pages/6_Auditor_Juridico_V2.py"),
        ("🧠 Panel Integral", "pages/13_Panel_Integral_Expediente.py"),
    ]
    for label, target in tool_links:
        st.markdown(f'<div class="lx-nav-item">{label}</div>', unsafe_allow_html=True)
        try:
            st.page_link(target, label=f"Abrir {label.split(' ', 1)[1]}", use_container_width=True)
        except Exception:
            pass

    st.markdown(
        '<div class="lx-status-bar">Estado: Online · Core v3.0</div>',
        unsafe_allow_html=True,
    )


casos = st.session_state.casos_despacho
metricas = _metricas(casos)

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
    with st.expander("Registrar nuevo caso", expanded=True):
        with st.form("nuevo_caso"):
            nombre = st.text_input("Nombre del asunto")
            cliente = st.text_input("Cliente")
            radicado = st.text_input("Radicación")
            estado = st.selectbox("Estado", list(STATUS_LABELS.keys()), format_func=lambda k: STATUS_LABELS[k])
            notas = st.text_area("Notas iniciales")
            if st.form_submit_button("Guardar caso"):
                if nombre.strip():
                    nuevo = {
                        "id": str(uuid4())[:8],
                        "nombre": nombre.strip(),
                        "cliente": cliente.strip() or "Sin cliente",
                        "radicado": radicado.strip() or "Sin radicado",
                        "estado": estado,
                        "tareas_abiertas": 0,
                        "vencidas": 0,
                        "eventos_7d": 0,
                        "minutos_sin_facturar": 0,
                        "notas": notas.strip(),
                        "proximo_evento": "",
                    }
                    st.session_state.casos_despacho.insert(0, nuevo)
                    st.session_state.caso_seleccionado_id = nuevo["id"]
                    st.session_state.mostrar_formulario_caso = False
                    st.rerun()
                else:
                    st.error("El nombre del asunto es obligatorio.")

st.markdown(
    f"""
    <div class="lx-metric-grid">
        <div class="lx-metric">
            <div class="lx-metric-label">Casos activos</div>
            <div class="lx-metric-value ok">{metricas['activos']}</div>
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
        <div class="lx-metric">
            <div class="lx-metric-label">Sin facturar</div>
            <div class="lx-metric-value">{metricas['sin_facturar']} min</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

filter_cols = st.columns(len(FILTER_OPTIONS))
for col, (key, label) in zip(filter_cols, FILTER_OPTIONS):
    with col:
        active = st.session_state.filtro_casos == key
        if st.button(label, key=f"filtro_{key}", use_container_width=True, type="primary" if active else "secondary"):
            st.session_state.filtro_casos = key
            st.rerun()

casos_filtrados = _filtrar_casos(casos)
if not any(c["id"] == st.session_state.caso_seleccionado_id for c in casos_filtrados):
    if casos_filtrados:
        st.session_state.caso_seleccionado_id = casos_filtrados[0]["id"]

lista_col, detalle_col = st.columns([1.1, 1.4])

with lista_col:
    st.markdown('<div class="lx-panel"><div class="lx-panel-title">Listado de casos</div>', unsafe_allow_html=True)
    if not casos_filtrados:
        st.markdown('<div class="lx-empty">No hay casos con este filtro.</div>', unsafe_allow_html=True)
    else:
        opciones = {c["id"]: f"{c['nombre']} — {c['cliente']}" for c in casos_filtrados}
        seleccion = st.radio(
            "Casos",
            options=list(opciones.keys()),
            format_func=lambda cid: opciones[cid],
            index=list(opciones.keys()).index(st.session_state.caso_seleccionado_id)
            if st.session_state.caso_seleccionado_id in opciones
            else 0,
            label_visibility="collapsed",
            key="radio_casos",
        )
        if seleccion != st.session_state.caso_seleccionado_id:
            st.session_state.caso_seleccionado_id = seleccion
            st.rerun()

        for caso in casos_filtrados:
            if caso["id"] != st.session_state.caso_seleccionado_id:
                continue
            badge = STATUS_LABELS.get(caso["estado"], caso["estado"])
            st.markdown(
                f'<span class="lx-badge {caso["estado"]}">{badge}</span>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

with detalle_col:
    seleccionado = next((c for c in casos if c["id"] == st.session_state.caso_seleccionado_id), None)
    st.markdown('<div class="lx-panel"><div class="lx-panel-title">Detalle del caso</div>', unsafe_allow_html=True)
    if not seleccionado:
        st.markdown(
            '<div class="lx-empty">Selecciona un caso para ver tareas, notas, eventos y tiempo.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"### {seleccionado['nombre']}")
        st.caption(f"{seleccionado['cliente']} · Rad. {seleccionado['radicado']}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tareas abiertas", seleccionado["tareas_abiertas"])
        m2.metric("Vencidas", seleccionado["vencidas"])
        m3.metric("Eventos 7d", seleccionado["eventos_7d"])
        m4.metric("Sin facturar", f"{seleccionado['minutos_sin_facturar']} min")

        tab_tareas, tab_notas, tab_eventos, tab_tiempo = st.tabs(
            ["Tareas", "Notas", "Eventos", "Tiempo"]
        )

        with tab_tareas:
            tareas = pd.DataFrame(
                [
                    {"Tarea": "Revisar memorial de impulso", "Estado": "Pendiente", "Vence": "Mañana"},
                    {"Tarea": "Actualizar cronología", "Estado": "En curso", "Vence": "3 días"},
                    {"Tarea": "Validar anexos PDF", "Estado": "Pendiente", "Vence": "5 días"},
                ][: max(seleccionado["tareas_abiertas"], 1)]
            )
            st.dataframe(tareas, use_container_width=True, hide_index=True)

        with tab_notas:
            st.text_area("Notas del caso", value=seleccionado.get("notas", ""), height=140, key=f"notas_{seleccionado['id']}")

        with tab_eventos:
            if seleccionado.get("proximo_evento"):
                st.info(f"Próximo evento: {seleccionado['proximo_evento']}")
            else:
                st.write("Sin eventos programados.")

        with tab_tiempo:
            st.number_input("Minutos registrados (sin facturar)", min_value=0, value=seleccionado["minutos_sin_facturar"], key=f"min_{seleccionado['id']}")

        st.divider()
        nuevo_estado = st.selectbox(
            "Cambiar estado",
            list(STATUS_LABELS.keys()),
            index=list(STATUS_LABELS.keys()).index(seleccionado["estado"]),
            format_func=lambda k: STATUS_LABELS[k],
            key=f"estado_{seleccionado['id']}",
        )
        if st.button("Actualizar estado", key=f"btn_estado_{seleccionado['id']}"):
            for caso in st.session_state.casos_despacho:
                if caso["id"] == seleccionado["id"]:
                    caso["estado"] = nuevo_estado
                    break
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
