from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from legal_analyzer.document_loader import load_document
from legal_analyzer.models import PageTrace
from legal_analyzer.ocr_engine import OCRConfig


st.set_page_config(
    page_title="Analizador Legal de Términos Colombia",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Analizador Legal de Términos Colombia")
st.caption(
    "Detecta el término, calcula cuándo vence y propone la actuación que puede continuar."
)

st.warning(
    "El resultado es preliminar. Debes confirmar la fecha efectiva de notificación, "
    "la regla de cómputo, los festivos y la norma aplicable."
)


NUMBER_WORDS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "quince": 15,
    "veinte": 20,
    "treinta": 30,
    "cuarenta": 40,
    "cuarenta y ocho": 48,
}


RULES = [
    {
        "clase": "Término judicial otorgado en auto o providencia",
        "regimen": "Proceso judicial / tutela",
        "norma": "Providencia judicial y regla procesal aplicable",
        "articulo": "Verificar artículo citado y artículo 118 CGP, si procede",
        "inicio": "Día siguiente a la notificación, salvo regla especial",
        "palabras": (
            "ordena",
            "requerir",
            "termino improrrogable",
            "dentro de",
            "plazo de",
            "vencido el termino",
        ),
    },
    {
        "clase": "Impugnación de fallo de tutela",
        "regimen": "Acción de tutela",
        "norma": "Decreto 2591 de 1991",
        "articulo": "Artículo 31",
        "inicio": "Notificación del fallo",
        "palabras": (
            "impugnacion",
            "impugnar",
            "fallo de tutela",
        ),
    },
    {
        "clase": "Respuesta general a derecho de petición",
        "regimen": "Derecho de petición",
        "norma": "Ley 1755 de 2015",
        "articulo": "Artículo 14",
        "inicio": "Recepción de la petición",
        "palabras": (
            "derecho de peticion",
            "peticion general",
        ),
    },
    {
        "clase": "Petición de documentos o información",
        "regimen": "Derecho de petición",
        "norma": "Ley 1755 de 2015",
        "articulo": "Artículo 14",
        "inicio": "Recepción de la petición",
        "palabras": (
            "solicitud de documentos",
            "solicitud de informacion",
            "copias",
            "expediente",
        ),
    },
    {
        "clase": "Recurso administrativo",
        "regimen": "Procedimiento administrativo",
        "norma": "Ley 1437 de 2011",
        "articulo": "Artículo 76",
        "inicio": "Notificación del acto administrativo",
        "palabras": (
            "recurso de reposicion",
            "recurso de apelacion",
            "acto administrativo",
        ),
    },
]


def norm(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text.translate(
            str.maketrans(
                "áéíóúüñÁÉÍÓÚÜÑ",
                "aeiouunAEIOUUN",
            )
        ).lower(),
    ).strip()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@st.cache_data(show_spinner=False, max_entries=40)
def cached_load(name, content_hash, content, enabled, min_chars, max_pages, dpi):
    del content_hash
    config = OCRConfig(
        enabled=enabled,
        min_useful_characters=min_chars,
        max_ocr_pages=max_pages,
        dpi=dpi,
    )
    return [item.to_dict() for item in load_document(name, content, config)]


def restore(data: dict) -> PageTrace:
    return PageTrace(**data)


def explicit_term(text: str) -> tuple[int | None, str | None, str]:
    clean = norm(text)

    word_pattern = (
        "cuarenta y ocho|cuarenta|treinta|veinte|quince|diez|"
        "nueve|ocho|siete|seis|cinco|cuatro|tres|dos|un|uno|una"
    )

    patterns = [
        (
            rf"(?:dentro de|por el termino de|"
            rf"termino(?: \w+){{0,4}} de|plazo(?: \w+){{0,4}} de)\s+"
            rf"(?P<number>{word_pattern}|\d{{1,3}})\s*"
            rf"(?P<unit>horas?|dias?)"
            rf"(?:\s*\((?P<paren>\d{{1,3}})\)\s*(?:horas?|dias?)?)?"
        ),
        (
            rf"\b(?P<number>{word_pattern}|\d{{1,3}})\s+"
            rf"(?P<unit>horas?|dias?)\s*"
            rf"(?:\((?P<paren>\d{{1,3}})\)\s*(?:horas?|dias?)?)?"
            rf"\s*(?:siguientes|habiles|calendario|improrrogables)?"
        ),
    ]

    for pattern in patterns:
        match = re.search(pattern, clean)

        if not match:
            continue

        raw_number = match.group("number").strip()
        parenthetical = match.groupdict().get("paren")

        if parenthetical:
            quantity = int(parenthetical)
        elif raw_number.isdigit():
            quantity = int(raw_number)
        else:
            quantity = NUMBER_WORDS.get(raw_number)

        if quantity is None:
            continue

        unit = "Horas" if "hora" in match.group("unit") else "Días"
        character = "Improrrogable" if "improrrogable" in clean else "Ordinario o por confirmar"

        return quantity, unit, character

    return None, None, ""


def action_detected(fragment: str) -> str:
    clean = norm(fragment)

    actions = (
        ("rendir informe o dictamen", ("informe", "dictamen")),
        ("pronunciarse", ("pronuncien", "pronunciarse")),
        ("dar cumplimiento", ("dar cumplimiento", "cumplimiento")),
        ("entregar", ("entregar", "entrega")),
        ("responder", ("responder", "respuesta")),
        ("aportar documentos", ("aportar", "allegar", "remitir")),
        ("impugnar", ("impugnar", "impugnacion")),
    )

    for label, words in actions:
        if any(word in clean for word in words):
            return label

    return "Actuación por confirmar"


def post_expiry_instruction(full_text: str) -> str:
    clean = norm(full_text)

    patterns = [
        r"vencido el termino[^\.]{0,350}",
        r"una vez vencido el termino[^\.]{0,350}",
        r"cumplido el termino[^\.]{0,350}",
    ]

    for pattern in patterns:
        match = re.search(pattern, clean)

        if match:
            return match.group(0).strip().capitalize()

    return ""


def classify(fragment: str) -> list[dict]:
    clean = norm(fragment)
    quantity, unit, character = explicit_term(fragment)

    if quantity is None:
        return []

    results = []

    for rule in RULES:
        hits = sum(word in clean for word in rule["palabras"])

        if hits == 0 and rule["clase"] != "Término judicial otorgado en auto o providencia":
            continue

        day_rule = "Por confirmar"

        if unit == "Horas":
            day_rule = "Horas continuas o por confirmar"
        elif "habil" in clean:
            day_rule = "Hábiles"
        elif "calendario" in clean:
            day_rule = "Calendario"

        results.append(
            {
                "Clase de término": rule["clase"],
                "Régimen jurídico": rule["regimen"],
                "Norma sugerida": rule["norma"],
                "Artículo": rule["articulo"],
                "Cantidad": quantity,
                "Unidad": unit,
                "Tipo de días": day_rule,
                "Carácter": character,
                "Hecho inicial sugerido": rule["inicio"],
                "Actuación exigida": action_detected(fragment),
                "Seguridad preliminar": min(95, 60 + hits * 10),
            }
        )

        if hits:
            break

    return results


def detect(pages: list[PageTrace]) -> list[dict]:
    full_text = "\n".join(page.text for page in pages)
    after_expiry = post_expiry_instruction(full_text)
    rows = []

    for page in pages:
        fragments = [
            item.strip()
            for item in re.split(r"(?<=[\.\;\:])\s+|\n+", page.text)
            if len(item.strip()) >= 20
        ]

        for fragment in fragments:
            for candidate in classify(fragment):
                rows.append(
                    {
                        "Documento": page.document,
                        "Página": page.page,
                        "Fragmento completo": fragment,
                        **candidate,
                        "Actuación indicada después del vencimiento": after_expiry,
                        "Fecha de notificación confirmada": None,
                        "Hora de notificación": time(8, 0),
                        "Regla de inicio": "Comienza al día siguiente",
                        "Aplicar cálculo": False,
                        "Conclusión revisada": "",
                    }
                )

    unique = []
    seen = set()

    for row in rows:
        key = (
            row["Documento"],
            row["Página"],
            row["Fragmento completo"],
            row["Clase de término"],
        )

        if key not in seen:
            seen.add(key)
            unique.append(row)

    return unique


def next_business_day(value: datetime, excluded: set[date]) -> datetime:
    current = value

    while current.weekday() >= 5 or current.date() in excluded:
        current += timedelta(days=1)

    return current


def calculate_deadline(
    notification: datetime,
    quantity: int,
    unit: str,
    day_rule: str,
    start_rule: str,
    excluded: set[date],
) -> tuple[datetime, datetime]:
    if start_rule == "Comienza al día siguiente":
        start = notification + timedelta(days=1)
    else:
        start = notification

    if unit == "Horas":
        return start, start + timedelta(hours=quantity)

    if day_rule == "Calendario":
        return start, start + timedelta(days=max(quantity - 1, 0))

    start = next_business_day(start, excluded)
    current = start
    counted = 1

    while counted < quantity:
        current += timedelta(days=1)

        if current.weekday() < 5 and current.date() not in excluded:
            counted += 1

    return start, current


def status(deadline: datetime) -> tuple[str, str, float]:
    hours = (deadline - datetime.now()).total_seconds() / 3600

    if hours < 0:
        return "Rojo", "Vencido", hours
    if hours <= 24:
        return "Rojo", "Urgente", hours
    if hours <= 72:
        return "Amarillo", "Próximo", hours

    return "Verde", "En plazo", hours


def continuation(
    row: pd.Series,
    deadline_state: str,
) -> str:
    required = str(row.get("Actuación exigida", ""))
    after_expiry = str(
        row.get(
            "Actuación indicada después del vencimiento",
            "",
        )
    )

    if deadline_state != "Vencido":
        return (
            f"Esperar el vencimiento y verificar si se presentó: {required}. "
            "Mientras tanto, revisar el expediente y preparar observaciones."
        )

    if after_expiry:
        return (
            f"Verificar que el despacho ejecute lo ordenado después del vencimiento: "
            f"{after_expiry}. Solicitar copia de la respuesta presentada y constancia "
            "de la actuación posterior."
        )

    clean = norm(required)

    if "informe" in clean or "dictamen" in clean:
        return (
            "Consultar si el informe o dictamen fue presentado. Si existe, solicitar copia "
            "y pronunciarse sobre su suficiencia. Si no existe, solicitar al juzgado que "
            "continúe el trámite, requiera el cumplimiento y adopte las medidas procedentes."
        )

    if "cumplimiento" in clean:
        return (
            "Solicitar verificación material del cumplimiento. Si continúa el incumplimiento, "
            "pedir medidas de cumplimiento y la continuación del incidente de desacato."
        )

    if "respuesta" in clean:
        return (
            "Verificar si se respondió de fondo. Si no hubo respuesta, preparar requerimiento, "
            "tutela o actuación procesal según el régimen identificado."
        )

    return (
        "Solicitar constancia de vencimiento, revisar si la parte obligada actuó y pedir "
        "que el despacho continúe con la etapa procesal correspondiente."
    )


with st.sidebar:
    st.header("OCR")
    enabled = st.checkbox("Aplicar OCR", value=True)
    min_chars = st.slider("Mínimo de caracteres útiles", 20, 300, 80, 10)
    max_pages = st.slider("Máximo de páginas OCR", 5, 100, 40, 5)
    dpi = st.select_slider(
        "Resolución OCR",
        [150, 200, 220, 250, 300],
        value=220,
    )


uploaded = st.file_uploader(
    "Sube el documento que quieres analizar",
    type=["pdf", "docx", "txt", "jpg", "jpeg", "png", "eml"],
)

if not uploaded:
    st.info("Sube un auto, fallo, requerimiento, notificación o constancia.")
    st.stop()


content = uploaded.getvalue()

with st.spinner("Analizando término, vencimiento y actuación posterior..."):
    raw = cached_load(
        uploaded.name,
        digest(content),
        content,
        enabled,
        min_chars,
        max_pages,
        dpi,
    )
    pages = [restore(item) for item in raw]
    rows = detect(pages)


if not rows:
    st.warning(
        "No se encontró un término expreso con las reglas actuales. "
        "Esto no demuestra que el documento no contenga términos."
    )
    st.stop()


st.success(f"Se detectaron {len(rows)} posible(s) término(s).")

data = pd.DataFrame(rows)

edited = st.data_editor(
    data,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Fragmento completo": st.column_config.TextColumn(
            "Fragmento completo",
            width="large",
        ),
        "Tipo de días": st.column_config.SelectboxColumn(
            "Tipo de días",
            options=[
                "Hábiles",
                "Calendario",
                "Horas continuas o por confirmar",
                "Por confirmar",
            ],
        ),
        "Fecha de notificación confirmada": st.column_config.DateColumn(
            "Fecha de notificación confirmada",
            format="YYYY-MM-DD",
        ),
        "Hora de notificación": st.column_config.TimeColumn(
            "Hora de notificación",
            format="HH:mm",
        ),
        "Regla de inicio": st.column_config.SelectboxColumn(
            "Regla de inicio",
            options=[
                "Comienza al día siguiente",
                "Comienza el mismo día",
            ],
        ),
        "Seguridad preliminar": st.column_config.ProgressColumn(
            "Seguridad preliminar",
            min_value=0,
            max_value=100,
            format="%d",
        ),
        "Aplicar cálculo": st.column_config.CheckboxColumn(
            "Calcular",
        ),
        "Conclusión revisada": st.column_config.TextColumn(
            "Conclusión revisada",
            width="large",
        ),
    },
    key="expiry_action_editor",
)


st.subheader("Explicación del documento")

for index, row in edited.iterrows():
    with st.expander(
        f"{index + 1}. {row['Clase de término']} — "
        f"{row['Documento']}, página {row['Página']}",
        expanded=index == 0,
    ):
        st.markdown(f"**Texto detectado:** {row['Fragmento completo']}")
        st.markdown(
            f"**Término:** {row['Cantidad']} {str(row['Unidad']).lower()} "
            f"— {row['Carácter']}"
        )
        st.markdown(f"**Actuación exigida:** {row['Actuación exigida']}")
        st.markdown(
            f"**Después del vencimiento:** "
            f"{row['Actuación indicada después del vencimiento'] or 'No se detectó instrucción expresa.'}"
        )
        st.markdown(
            f"**Norma sugerida:** {row['Norma sugerida']} — {row['Artículo']}"
        )


st.subheader("Calcular vencimiento y actuación siguiente")

excluded_text = st.text_area(
    "Festivos o fechas excluidas",
    placeholder="Una por línea: AAAA-MM-DD",
    height=90,
)

if st.button(
    "Calcular términos seleccionados",
    type="primary",
    use_container_width=True,
):
    excluded = set()
    invalid = []

    for line in excluded_text.splitlines():
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
        results = []

        for _, row in edited.iterrows():
            if not bool(row["Aplicar cálculo"]):
                continue

            notification_date = row["Fecha de notificación confirmada"]

            if pd.isna(notification_date):
                st.warning(
                    f"Falta la fecha de notificación de: {row['Clase de término']}."
                )
                continue

            if row["Tipo de días"] == "Por confirmar":
                st.warning(
                    f"Confirma si el término usa días hábiles o calendario: "
                    f"{row['Clase de término']}."
                )
                continue

            if isinstance(notification_date, pd.Timestamp):
                notification_date = notification_date.date()

            notification_time = row["Hora de notificación"]

            if pd.isna(notification_time):
                notification_time = time(8, 0)

            notification = datetime.combine(
                notification_date,
                notification_time,
            )

            day_rule = (
                "Hábiles"
                if row["Tipo de días"] == "Horas continuas o por confirmar"
                else row["Tipo de días"]
            )

            start, deadline = calculate_deadline(
                notification=notification,
                quantity=int(row["Cantidad"]),
                unit=row["Unidad"],
                day_rule=day_rule,
                start_rule=row["Regla de inicio"],
                excluded=excluded,
            )

            color, deadline_state, remaining_hours = status(deadline)

            results.append(
                {
                    "Documento": row["Documento"],
                    "Página": row["Página"],
                    "Clase de término": row["Clase de término"],
                    "Actuación exigida": row["Actuación exigida"],
                    "Fecha de notificación": notification,
                    "Inicio del cómputo": start,
                    "Vencimiento estimado": deadline,
                    "Semáforo": color,
                    "Estado": deadline_state,
                    "Horas restantes": round(remaining_hours, 1),
                    "Actuación que puede continuar": continuation(
                        row,
                        deadline_state,
                    ),
                    "Advertencia": (
                        "Confirmar festivos, horario judicial, forma de notificación "
                        "y cualquier regla especial."
                    ),
                }
            )

        if results:
            result_df = pd.DataFrame(results)
            st.session_state["expiry_action_results"] = result_df

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )

            for _, result in result_df.iterrows():
                icon = {
                    "Rojo": "🔴",
                    "Amarillo": "🟡",
                    "Verde": "🟢",
                }[result["Semáforo"]]

                st.info(
                    f"{icon} **Vencimiento:** {result['Vencimiento estimado']}\n\n"
                    f"**Estado:** {result['Estado']}\n\n"
                    f"**Actuación que puede continuar:** "
                    f"{result['Actuación que puede continuar']}"
                )
        else:
            st.info("No seleccionaste un término listo para calcular.")


st.subheader("Exportar")

results_df = st.session_state.get(
    "expiry_action_results",
    pd.DataFrame(),
)

excel = io.BytesIO()

with pd.ExcelWriter(excel, engine="openpyxl") as writer:
    edited.to_excel(
        writer,
        sheet_name="Términos detectados",
        index=False,
    )
    results_df.to_excel(
        writer,
        sheet_name="Vencimientos y actuación",
        index=False,
    )

st.download_button(
    "Descargar análisis en Excel",
    data=excel.getvalue(),
    file_name="terminos_vencimientos_actuaciones.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
