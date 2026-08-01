from __future__ import annotations

import io
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
from docx import Document
from docx.shared import Pt


st.set_page_config(
    page_title="Control de Términos",
    page_icon="⏳",
    layout="wide",
)

st.title("⏳ Control de Términos y Próxima Actuación")
st.caption(
    "Registra vencimientos, identifica urgencias y ordena lo que debes presentar."
)
st.warning(
    "El cálculo depende de los datos que confirmes. Verifica siempre la norma, "
    "la fecha inicial, la notificación y la regla de cómputo."
)


def calculate_deadline(start, quantity, unit, rule, excluded):
    if unit == "Horas":
        return start + timedelta(hours=quantity)

    if rule == "Calendario":
        return start + timedelta(days=quantity)

    current = start
    counted = 0

    while counted < quantity:
        current += timedelta(days=1)

        if current.weekday() < 5 and current.date() not in excluded:
            counted += 1

    return current


def status_for(deadline):
    hours = (deadline - datetime.now()).total_seconds() / 3600

    if hours < 0:
        return "Rojo", "Vencido", hours
    if hours <= 24:
        return "Rojo", "Urgente", hours
    if hours <= 72:
        return "Amarillo", "Próximo", hours

    return "Verde", "En plazo", hours


def remaining_text(hours):
    if hours < 0:
        return f"Vencido hace {abs(hours):.1f} horas"

    days = int(hours // 24)
    extra = hours % 24

    if days:
        return f"{days} día(s) y {extra:.1f} hora(s)"

    return f"{extra:.1f} hora(s)"


def suggested_action(color, action):
    action = action or "la actuación pendiente"

    if color == "Rojo":
        return (
            f"Verificar inmediatamente el cómputo y preparar {action}, "
            "con anexos y prueba de envío."
        )

    if color == "Amarillo":
        return (
            f"Dejar listo el borrador de {action} y confirmar hoy la fecha exacta."
        )

    return (
        f"Programar la preparación de {action} y conservar el soporte de la fecha inicial."
    )


if "terms" not in st.session_state:
    st.session_state.terms = []


with st.form("new_term"):
    st.subheader("1. Registrar término")

    c1, c2, c3 = st.columns(3)

    with c1:
        expediente = st.text_input("Expediente")
        radicado = st.text_input("Radicado")
        actuacion = st.text_input(
            "Próxima actuación",
            placeholder="Ejemplo: incidente de desacato",
        )

    with c2:
        hecho = st.text_input(
            "Hecho que inicia el término",
            placeholder="Ejemplo: notificación del auto",
        )
        fecha = st.date_input("Fecha inicial", value=date.today())
        hora = st.time_input("Hora inicial", value=time(8, 0))

    with c3:
        cantidad = st.number_input(
            "Cantidad",
            min_value=0,
            value=1,
            step=1,
        )
        unidad = st.selectbox("Unidad", ["Días", "Horas"])
        regla = st.selectbox(
            "Regla",
            ["Hábiles", "Calendario"],
            disabled=unidad == "Horas",
        )

    excluidas = st.text_area(
        "Fechas excluidas adicionales",
        placeholder="Una por línea: AAAA-MM-DD",
        height=90,
    )

    soporte = st.text_area(
        "Soporte de la fecha inicial",
        placeholder="Documento, página, correo o constancia de notificación.",
        height=90,
    )

    guardar = st.form_submit_button(
        "Calcular y guardar",
        type="primary",
        use_container_width=True,
    )


if guardar:
    excluded = set()
    invalid = []

    for line in excluidas.splitlines():
        value = line.strip()

        if not value:
            continue

        try:
            excluded.add(datetime.strptime(value, "%Y-%m-%d").date())
        except ValueError:
            invalid.append(value)

    if invalid:
        st.error("Fechas inválidas: " + ", ".join(invalid))
    else:
        start = datetime.combine(fecha, hora)
        deadline = calculate_deadline(
            start,
            int(cantidad),
            unidad,
            regla,
            excluded,
        )
        color, state, hours = status_for(deadline)

        st.session_state.terms.append(
            {
                "Expediente": expediente,
                "Radicado": radicado,
                "Actuación": actuacion,
                "Hecho inicial": hecho,
                "Fecha inicial": start,
                "Término": f"{int(cantidad)} {unidad.lower()}",
                "Regla": regla if unidad == "Días" else "Horas continuas",
                "Vencimiento": deadline,
                "Semáforo": color,
                "Estado": state,
                "Tiempo restante": remaining_text(hours),
                "Qué hacer": suggested_action(color, actuacion),
                "Soporte": soporte,
                "Revisión humana": "",
            }
        )

        st.success(f"Vencimiento calculado: {deadline:%Y-%m-%d %H:%M}")


st.subheader("2. Agenda procesal")

if not st.session_state.terms:
    st.info("Todavía no hay términos registrados.")
    st.stop()


table = pd.DataFrame(st.session_state.terms)

priority = {"Rojo": 0, "Amarillo": 1, "Verde": 2}
table["_orden"] = table["Semáforo"].map(priority).fillna(9)
table = table.sort_values(
    ["_orden", "Vencimiento"],
    ascending=[True, True],
).drop(columns="_orden")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total", len(table))
c2.metric("🔴 Urgentes", int((table["Semáforo"] == "Rojo").sum()))
c3.metric("🟡 Próximos", int((table["Semáforo"] == "Amarillo").sum()))
c4.metric("🟢 En plazo", int((table["Semáforo"] == "Verde").sum()))

edited = st.data_editor(
    table,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Fecha inicial": st.column_config.DatetimeColumn(
            "Fecha inicial",
            format="YYYY-MM-DD HH:mm",
        ),
        "Vencimiento": st.column_config.DatetimeColumn(
            "Vencimiento",
            format="YYYY-MM-DD HH:mm",
        ),
        "Semáforo": st.column_config.SelectboxColumn(
            "Semáforo",
            options=["Rojo", "Amarillo", "Verde"],
        ),
        "Revisión humana": st.column_config.TextColumn(
            "Revisión humana",
            width="large",
        ),
    },
    key="terms_editor",
)


st.subheader("3. Qué hacer primero")

urgent = edited[edited["Semáforo"].isin(["Rojo", "Amarillo"])]

if urgent.empty:
    st.success("No hay vencimientos urgentes.")
else:
    for _, row in urgent.iterrows():
        icon = "🔴" if row["Semáforo"] == "Rojo" else "🟡"
        st.warning(
            f"{icon} **{row['Expediente'] or 'Expediente sin nombre'}**\n\n"
            f"**Actuación:** {row['Actuación'] or 'Sin definir'}\n\n"
            f"**Vencimiento:** {row['Vencimiento']}\n\n"
            f"**Acción:** {row['Qué hacer']}"
        )


st.subheader("4. Exportar")

excel = io.BytesIO()

with pd.ExcelWriter(excel, engine="openpyxl") as writer:
    edited.to_excel(
        writer,
        sheet_name="Control de términos",
        index=False,
    )


def create_word(dataframe):
    document = Document()
    document.styles["Normal"].font.name = "Arial"
    document.styles["Normal"].font.size = Pt(10)
    document.add_heading(
        "CONTROL DE TÉRMINOS Y PRÓXIMAS ACTUACIONES",
        level=0,
    )

    for index, row in dataframe.iterrows():
        document.add_heading(
            f"{index + 1}. {row.get('Expediente', '')}",
            level=1,
        )

        for label, field in (
            ("Radicado", "Radicado"),
            ("Actuación", "Actuación"),
            ("Fecha inicial", "Fecha inicial"),
            ("Vencimiento", "Vencimiento"),
            ("Estado", "Estado"),
            ("Semáforo", "Semáforo"),
            ("Qué hacer", "Qué hacer"),
            ("Soporte", "Soporte"),
        ):
            document.add_paragraph(
                f"{label}: {row.get(field, '')}"
            )

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


d1, d2 = st.columns(2)

with d1:
    st.download_button(
        "Descargar agenda en Excel",
        data=excel.getvalue(),
        file_name="control_terminos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with d2:
    st.download_button(
        "Descargar agenda en Word",
        data=create_word(edited),
        file_name="control_terminos.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )

if st.button("Eliminar todos los términos"):
    st.session_state.terms = []
    st.rerun()
