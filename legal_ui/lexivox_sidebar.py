from __future__ import annotations

import streamlit as st

VISTAS = [
    ("casos", "📁 Casos"),
    ("clientes", "👥 Clientes"),
    ("tareas", "✅ Tareas"),
    ("calendario", "📅 Calendario"),
]


def render_lexivox_sidebar(vista_activa: str, buscar: str = "") -> str:
    st.markdown('<div class="lx-brand">Lexivox</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="lx-brand-sub">Gestión de expedientes judiciales</div>',
        unsafe_allow_html=True,
    )
    query = st.text_input(
        "Buscar",
        value=buscar,
        placeholder="Radicado, cliente, asunto...",
        label_visibility="collapsed",
        key="lexivox_buscar",
    )

    st.markdown('<div class="lx-nav-section">PRINCIPAL</div>', unsafe_allow_html=True)
    for key, label in VISTAS:
        css_class = "lx-nav-item active" if vista_activa == key else "lx-nav-item"
        st.markdown(f'<div class="{css_class}">{label}</div>', unsafe_allow_html=True)
        if vista_activa != key and st.button(f"Abrir {label.split(' ', 1)[1]}", key=f"nav_{key}", use_container_width=True):
            st.session_state.lexivox_vista = key
            st.rerun()

    st.markdown('<div class="lx-nav-section">APLICACIÓN</div>', unsafe_allow_html=True)
    for label, target in [
        ("🏠 Inicio", "🏠_Inicio.py"),
        ("🤖 Asistente Legal", "pages/2_🤖_Experto_en_Expediente_Electronico.py"),
    ]:
        st.markdown(f'<div class="lx-nav-item">{label}</div>', unsafe_allow_html=True)
        try:
            st.page_link(target, label=f"Ir a {label.split(' ', 1)[1]}", use_container_width=True)
        except Exception:
            pass

    st.markdown('<div class="lx-nav-section">HERRAMIENTAS</div>', unsafe_allow_html=True)
    for label, target in [
        ("📚 Organizador Vigilancia", "pages/24_Organizador_Automatico_Vigilancia.py"),
        ("⚖️ Auditor Jurídico V2", "pages/6_Auditor_Juridico_V2.py"),
        ("🧠 Panel Integral", "pages/13_Panel_Integral_Expediente.py"),
    ]:
        st.markdown(f'<div class="lx-nav-item">{label}</div>', unsafe_allow_html=True)
        try:
            st.page_link(target, label=f"Abrir {label.split(' ', 1)[1]}", use_container_width=True)
        except Exception:
            pass

    st.markdown(
        '<div class="lx-status-bar">Estado: Online · Core v3.0 · Datos locales JSON/Excel</div>',
        unsafe_allow_html=True,
    )
    return query.strip().lower()
