from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timedelta, time

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
    "Sube un documento, identifica posibles términos jurídicos, "
    "revisa la norma sugerida y confirma el cómputo."
)

st.warning(
    "La clasificación es preliminar. Debes confirmar el régimen, la norma, "
    "la fecha de notificación y la regla de cómputo antes de usar el resultado."
)


RULES = [
    {
        "clase": "Impugnación de fallo de tutela",
        "regimen": "Acción de tutela",
        "norma": "Decreto 2591 de 1991",
        "articulo": "Artículo 31",
        "cantidad": 3,
        "unidad": "Días",
        "dias": "Por confirmar",
        "inicio": "Notificación del fallo",
        "palabras": (
            "impugnacion",
            "impugnar",
            "fallo de tutela",
        ),
        "advertencia": (
            "Debe verificarse la fecha de notificación. "
            "La impugnación no suspende el cumplimiento inmediato del fallo."
        ),
    },
    {
        "clase": "Respuesta general a derecho de petición",
        "regimen": "Derecho de petición",
        "norma": "Ley 1755 de 2015",
        "articulo": "Artículo 14",
        "cantidad": 15,
        "unidad": "Días",
        "dias": "Hábiles",
        "inicio": "Recepción de la petición",
        "palabras": (
            "derecho de peticion",
            "peticion general",
        ),
        "advertencia": "Puede existir un término especial según la materia.",
    },
    {
        "clase": "Petición de documentos o información",
        "regimen": "Derecho de petición",
        "norma": "Ley 1755 de 2015",
        "articulo": "Artículo 14",
        "cantidad": 10,
        "unidad": "Días",
        "dias": "Hábiles",
        "inicio": "Recepción de la petición",
        "palabras": (
            "solicitud de documentos",
            "solicitud de informacion",
            "expediente",
            "copias",
        ),
        "advertencia": (
            "Debe confirmarse que la solicitud sea realmente de documentos o información."
        ),
    },
    {
        "clase": "Consulta a una autoridad",
        "regimen": "Derecho de petición",
        "norma": "Ley 1755 de 2015",
        "articulo": "Artículo 14",
        "cantidad": 30,
        "unidad": "Días",
        "dias": "Hábiles",
        "inicio": "Recepción de la consulta",
        "palabras": (
            "consulta",
            "concepto juridico",
        ),
        "advertencia": "No toda petición debe clasificarse como consulta.",
    },
    {
        "clase": "Recurso de reposición o apelación administrativo",
        "regimen": "Procedimiento administrativo",
        "norma": "Ley 1437 de 2011",
        "articulo": "Artículo 76",
        "cantidad": 10,
        "unidad": "Días",
        "dias": "Hábiles",
        "inicio": "Notificación del acto administrativo",
        "palabras": (
            "recurso de reposicion",
            "recurso de apelacion",
            "acto administrativo",
        ),
        "advertencia": (
            "Debe verificarse la procedencia del recurso y la forma de notificación."
        ),
    },
    {
        "clase": "Notificación personal electrónica judicial",
        "regimen": "Proceso judicial digital",
        "norma": "Ley 2213 de 2022",
        "articulo": "Artículo 8",
        "cantidad": 2,
        "unidad": "Días",
        "dias": "Hábiles",
        "inicio": "Envío del mensaje de datos",
        "palabras": (
            "notificacion personal",
            "mensaje de datos",
            "correo electronico",
        ),
        "advertencia": (
            "Debe verificarse cuándo se entiende realizada la notificación "
            "y desde cuándo inicia el término principal."
        ),
    },
    {
        "clase": "Término judicial otorgado por providencia",
        "regimen": "Proceso judicial",
        "norma": "Ley 1564 de 2012",
        "articulo": "Artículo 118",
        "cantidad": 0,
        "unidad": "Días",
        "dias": "Por confirmar",
        "inicio": "Notificación, audiencia o ejecutoria, según el caso",
        "palabras": (
            "termino de",
            "traslado",
            "ejecutoria",
            "dentro de",
            "plazo de",
        ),
        "advertencia": (
            "El artículo 118 contiene reglas distintas. "
            "Debe identificarse cómo fue concedido el término."
        ),
    },
]


def norm(text: str) -> str:
    return (
        text.translate(
            str.maketrans(
                "áéíóúüñÁÉÍÓÚÜÑ",
                "aeiouunAEIOUUN",
            )
        )
        .lower()
    )


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
    return [x.to_dict() for x in load_document(name, content, config)]


def restore(data: dict) -> PageTrace:
    return PageTrace(**data)


def explicit_term(text: str):
    """
    Detecta términos escritos con números, palabras y formatos judiciales como:
    - "en el término improrrogable de UN DÍA"
    - "UN DÍA (01) DÍA"
    - "dentro de cuarenta y ocho (48) horas"
    - "por el término de tres (3) días"
    """
    clean = norm(text)

    number_words = {
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
        "cuarenta y ocho": 48,
        "cuarenta": 40,
        "cuarenta y cinco": 45,
    }

    flexible_patterns = [
        (
            r"(?:dentro\s+de|por\s+el\s+termino\s+de|"
            r"termino(?:\s+\w+){0,4}\s+de|"
            r"plazo(?:\s+\w+){0,4}\s+de)\s+"
            r"(?P<word>cuarenta\s+y\s+ocho|cuarenta\s+y\s+cinco|"
            r"un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|"
            r"nueve|diez|quince|veinte|treinta|cuarenta|\d{1,3})"
            r"\s*(?P<unit>horas?|dias?)"
            r"(?:\s*\((?P<paren>\d{1,3})\)\s*(?:horas?|dias?)?)?"
        ),
        (
            r"\b(?P<word>\d{1,3})\s*(?P<unit>horas?|dias?)\s+"
            r"(?:siguientes|habiles|calendario|improrrogables)"
        ),
    ]

    for pattern in flexible_patterns:
        match = re.search(pattern, clean)

        if not match:
            continue

        word = match.group("word").strip()
        parenthetical = match.groupdict().get("paren")

        if parenthetical:
            quantity = int(parenthetical)
        elif word.isdigit():
            quantity = int(word)
        else:
            quantity = number_words.get(word)

        if quantity is None:
            continue

        unit_text = match.group("unit")
        unit = "Horas" if "hora" in unit_text else "Días"

        return quantity, unit

    # Formato frecuente: "UN DIA (01) DÍA"
    repeated = re.search(
        r"\b(?P<word>un|uno|una|dos|tres|\d{1,3})\s+"
        r"(?P<unit>horas?|dias?)\s*"
        r"\((?P<paren>\d{1,3})\)\s*(?:horas?|dias?)?",
        clean,
    )

    if repeated:
        quantity = int(repeated.group("paren"))
        unit = (
            "Horas"
            if "hora" in repeated.group("unit")
            else "Días"
        )
        return quantity, unit

    return None, None


def detect(pages: list[PageTrace]) -> list[dict]:
    rows = []

    for page in pages:
        fragments = [
            x.strip()
            for x in re.split(r"(?<=[\.\;\:])\s+|\n+", page.text)
            if len(x.strip()) >= 25
        ]

        for fragment in fragments:
            clean = norm(fragment)
            quantity_found, unit_found = explicit_term(fragment)

            for rule in RULES:
                hits = sum(word in clean for word in rule["palabras"])

                # Si el fragmento contiene un plazo expreso, se analiza aunque
                # no coincida literalmente con las palabras clave de la regla.
                if hits == 0 and quantity_found is None:
                    continue

                day_rule = rule["dias"]

                if "habil" in clean:
                    day_rule = "Hábiles"
                elif "calendario" in clean:
                    day_rule = "Calendario"

                rows.append(
                    {
                        "Documento": page.document,
                        "Página": page.page,
                        "Fragmento completo": fragment,
                        "Clase de término": rule["clase"],
                        "Régimen jurídico": rule["regimen"],
                        "Norma sugerida": rule["norma"],
                        "Artículo": rule["articulo"],
                        "Cantidad": (
                            quantity_found
                            if quantity_found is not None
                            else rule["cantidad"]
                        ),
                        "Unidad": (
                            unit_found
                            if unit_found is not None
                            else rule["unidad"]
                        ),
                        "Tipo de días": day_rule,
                        "Hecho inicial sugerido": rule["inicio"],
                        "Seguridad preliminar": min(
                            95,
                            55 + hits * 15
                            if quantity_found is not None
                            else 35 + hits * 20,
                        ),
                        "Advertencia jurídica": rule["advertencia"],
                        "Fecha inicial confirmada": None,
                        "Hora inicial": time(8, 0),
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


def calculate(start, quantity, unit, day_rule, excluded):
    if unit == "Horas":
        return start + timedelta(hours=int(quantity))

    if day_rule == "Calendario":
        return start + timedelta(days=int(quantity))

    current = start
    count = 0

    while count < int(quantity):
        current += timedelta(days=1)
        if current.weekday() < 5 and current.date() not in excluded:
            count += 1

    return current


def semaphore(deadline):
    hours = (deadline - datetime.now()).total_seconds() / 3600

    if hours < 0:
        return "Rojo", "Vencido"
    if hours <= 24:
        return "Rojo", "Urgente"
    if hours <= 72:
        return "Amarillo", "Próximo"
    return "Verde", "En plazo"


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
    st.info(
        "Puedes subir autos, fallos, derechos de petición, actos administrativos, "
        "recursos, notificaciones y constancias."
    )
    st.stop()


content = uploaded.getvalue()

with st.spinner("Analizando el documento..."):
    raw = cached_load(
        uploaded.name,
        digest(content),
        content,
        enabled,
        min_chars,
        max_pages,
        dpi,
    )
    pages = [restore(x) for x in raw]
    rows = detect(pages)


if not rows:
    st.warning(
        "No se encontró una coincidencia suficiente. "
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
            options=["Hábiles", "Calendario", "Por confirmar"],
        ),
        "Fecha inicial confirmada": st.column_config.DateColumn(
            "Fecha inicial confirmada",
            format="YYYY-MM-DD",
        ),
        "Hora inicial": st.column_config.TimeColumn(
            "Hora inicial",
            format="HH:mm",
        ),
        "Seguridad preliminar": st.column_config.ProgressColumn(
            "Seguridad preliminar",
            min_value=0,
            max_value=100,
            format="%d",
        ),
        "Aplicar cálculo": st.column_config.CheckboxColumn(
            "Aplicar cálculo",
        ),
        "Conclusión revisada": st.column_config.TextColumn(
            "Conclusión revisada",
            width="large",
        ),
    },
    key="legal_term_editor",
)


st.subheader("Explicación jurídica preliminar")

for index, row in edited.iterrows():
    with st.expander(
        f"{index + 1}. {row['Clase de término']} — "
        f"{row['Documento']}, página {row['Página']}",
        expanded=index == 0,
    ):
        st.markdown(f"**Fragmento:** {row['Fragmento completo']}")
        st.markdown(f"**Régimen:** {row['Régimen jurídico']}")
        st.markdown(
            f"**Norma sugerida:** {row['Norma sugerida']}, {row['Artículo']}"
        )
        st.markdown(
            f"**Cantidad:** {row['Cantidad']} {str(row['Unidad']).lower()}"
        )
        st.markdown(f"**Tipo de días:** {row['Tipo de días']}")
        st.markdown(
            f"**Hecho inicial sugerido:** {row['Hecho inicial sugerido']}"
        )
        st.warning(row["Advertencia jurídica"])


st.subheader("Cálculo confirmado")

excluded_text = st.text_area(
    "Fechas excluidas adicionales",
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

            start_date = row["Fecha inicial confirmada"]

            if pd.isna(start_date):
                st.warning(
                    f"Falta confirmar la fecha inicial de: {row['Clase de término']}."
                )
                continue

            if row["Tipo de días"] == "Por confirmar":
                st.warning(
                    f"Falta confirmar el tipo de días de: {row['Clase de término']}."
                )
                continue

            if int(row["Cantidad"]) <= 0:
                st.warning(
                    f"Falta confirmar la cantidad de: {row['Clase de término']}."
                )
                continue

            if isinstance(start_date, pd.Timestamp):
                start_date = start_date.date()

            start_time = row["Hora inicial"]

            if pd.isna(start_time):
                start_time = time(8, 0)

            start = datetime.combine(start_date, start_time)
            deadline = calculate(
                start,
                row["Cantidad"],
                row["Unidad"],
                row["Tipo de días"],
                excluded,
            )

            color, status = semaphore(deadline)

            results.append(
                {
                    "Clase de término": row["Clase de término"],
                    "Documento": row["Documento"],
                    "Página": row["Página"],
                    "Norma sugerida": (
                        f"{row['Norma sugerida']}, {row['Artículo']}"
                    ),
                    "Fecha inicial": start,
                    "Vencimiento estimado": deadline,
                    "Semáforo": color,
                    "Estado": status,
                    "Advertencia": row["Advertencia jurídica"],
                }
            )

        if results:
            result_df = pd.DataFrame(results)
            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )
            st.session_state["legal_term_results"] = result_df
        else:
            st.info("No hay términos confirmados para calcular.")


st.subheader("Exportar")

calculated = st.session_state.get(
    "legal_term_results",
    pd.DataFrame(),
)

excel = io.BytesIO()

with pd.ExcelWriter(excel, engine="openpyxl") as writer:
    edited.to_excel(
        writer,
        sheet_name="Análisis legal",
        index=False,
    )
    calculated.to_excel(
        writer,
        sheet_name="Cálculos",
        index=False,
    )

st.download_button(
    "Descargar análisis legal en Excel",
    data=excel.getvalue(),
    file_name="analisis_legal_terminos_colombia.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

