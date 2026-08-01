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
    page_title="Revisor Integral de Vigilancia",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Revisor Integral de Vigilancia Judicial")
st.caption(
    "Carga documentos, formula una pregunta y recibe una respuesta sustentada; "
    "además revisa errores, términos y posibles conductas relevantes."
)

st.error(
    "Los resultados son preliminares. El sistema identifica indicios, no declara "
    "responsabilidad del despacho ni reemplaza recursos, incidentes o asesoría jurídica."
)


MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "quince": 15,
    "veinte": 20, "treinta": 30, "cuarenta y ocho": 48,
}

CONDUCTS = [
    {
        "name": "Mora o inactividad aparente",
        "terms": (
            "pendiente de decision", "sin resolver", "no se ha resuelto",
            "pase a despacho", "se encuentra a despacho", "mora",
            "sin pronunciamiento", "vencido el termino",
        ),
        "norm": "Ley 270 de 1996, artículos 4 y 7; Acuerdo PSAA11-8716 de 2011",
        "purpose": "Revisar oportunidad, celeridad y eficacia de la gestión.",
    },
    {
        "name": "Falta de trámite de memorial o solicitud",
        "terms": (
            "memorial de impulso", "solicitud de decision",
            "solicitud sin respuesta", "peticion sin respuesta",
            "no se dio tramite",
        ),
        "norm": "Constitución, artículos 29 y 229; Ley 270 de 1996",
        "purpose": "Verificar si una actuación presentada quedó sin gestión.",
    },
    {
        "name": "Notificación posiblemente incompleta",
        "terms": (
            "notificar", "correo electronico", "mensaje de datos",
            "sin constancia de notificacion", "no fue notificado",
        ),
        "norm": "Norma procesal aplicable; Ley 2213 de 2022, artículo 8, según el caso",
        "purpose": "Comprobar envío, entrega, acceso y fecha de inicio del término.",
    },
    {
        "name": "Seguimiento insuficiente del cumplimiento de tutela",
        "terms": (
            "incidente de desacato", "incumplimiento del fallo",
            "dar cumplimiento", "continua el incumplimiento",
            "no se cumplio la tutela",
        ),
        "norm": "Decreto 2591 de 1991, artículos 27 y 52",
        "purpose": "Verificar medidas para lograr el cumplimiento efectivo.",
    },
]

ERROR_RULES = [
    {
        "name": "Radicados diferentes dentro del expediente",
        "category": "Error fáctico o de identificación",
        "norm": "Constitución Política, artículo 29",
    },
    {
        "name": "Fechas incompatibles o futuras",
        "category": "Error fáctico",
        "norm": "Constitución Política, artículo 29",
    },
    {
        "name": "Confusión del objeto ordenado o entregado",
        "category": "Error fáctico y de congruencia",
        "norm": "Constitución Política, artículo 29",
    },
    {
        "name": "Afirmación de falta de prueba pese a referencias a anexos",
        "category": "Posible omisión probatoria",
        "norm": "Constitución Política, artículo 29",
    },
]


def normalize(text: str) -> str:
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


@st.cache_data(show_spinner=False, max_entries=200)
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


def extract_dates(text: str) -> list[date]:
    clean = normalize(text)
    values = []

    for day, month, year in re.findall(
        r"\b([0-3]?\d)[/-]([01]?\d)[/-]((?:19|20)\d{2})\b",
        clean,
    ):
        try:
            values.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass

    pattern = (
        r"\b([0-3]?\d)\s+de\s+("
        + "|".join(MONTHS.keys())
        + r")\s+de\s+((?:19|20)\d{2})\b"
    )

    for day, month_name, year in re.findall(pattern, clean):
        try:
            values.append(date(int(year), MONTHS[month_name], int(day)))
        except ValueError:
            pass

    judicial = (
        r"\(([0-3]?\d)\)\s+de\s+("
        + "|".join(MONTHS.keys())
        + r")\s+de\s+[^()\n]{0,100}\(((?:19|20)\d{2})\)"
    )

    for day, month_name, year in re.findall(judicial, clean):
        try:
            values.append(date(int(year), MONTHS[month_name], int(day)))
        except ValueError:
            pass

    return list(dict.fromkeys(values))


def extract_radications(text: str) -> list[str]:
    patterns = [
        r"\b\d{2}-\d{3}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}\b",
        r"\b\d{23}\b",
    ]
    values = []
    for pattern in patterns:
        values.extend(re.findall(pattern, text))
    return list(dict.fromkeys(values))


def detect_terms(document: str, pages: list[PageTrace]) -> list[dict]:
    rows = []
    word_pattern = (
        "cuarenta y ocho|treinta|veinte|quince|diez|nueve|ocho|"
        "siete|seis|cinco|cuatro|tres|dos|un|uno|una"
    )
    pattern = (
        rf"(?:dentro de|termino(?: \w+){{0,4}} de|plazo(?: \w+){{0,4}} de)\s+"
        rf"(?P<number>{word_pattern}|\d{{1,3}})\s*"
        rf"(?P<unit>horas?|dias?)"
        rf"(?:\s*\((?P<paren>\d{{1,3}})\)\s*(?:horas?|dias?)?)?"
    )

    document_date = None
    full_text = "\n".join(page.text or "" for page in pages)
    dates = extract_dates(full_text)
    if dates:
        document_date = dates[0]

    for page in pages:
        fragments = [
            item.strip()
            for item in re.split(r"(?<=[.;:])\s+|\n+", page.text or "")
            if len(item.strip()) >= 20
        ]

        for fragment in fragments:
            clean = normalize(fragment)
            match = re.search(pattern, clean)
            if not match:
                continue

            raw_number = match.group("number")
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
            day_rule = "Calendario" if "calendario" in clean else "Hábiles"
            start = None
            deadline = None

            if document_date:
                start = datetime.combine(
                    document_date + timedelta(days=1),
                    time(8, 0),
                )

                if unit == "Horas":
                    deadline = start + timedelta(hours=quantity)
                elif day_rule == "Calendario":
                    deadline = start + timedelta(days=max(quantity - 1, 0))
                else:
                    current = start
                    counted = 1
                    while counted < quantity:
                        current += timedelta(days=1)
                        if current.weekday() < 5:
                            counted += 1
                    deadline = current

            rows.append({
                "Documento": document,
                "Página": page.page,
                "Fragmento": fragment,
                "Cantidad": quantity,
                "Unidad": unit,
                "Tipo de días": day_rule,
                "Fecha del escrito usada": document_date,
                "Inicio estimado": start,
                "Vencimiento estimado": deadline,
                "Estado": (
                    "Vencido"
                    if deadline and deadline < datetime.now()
                    else "En plazo o por confirmar"
                ),
                "Advertencia": (
                    "El cálculo usa la fecha del escrito. Confirmar notificación, "
                    "ejecutoria, festivos y regla especial."
                ),
            })

    return rows


def detect_errors(document: str, pages: list[PageTrace]) -> list[dict]:
    findings = []
    full_text = "\n".join(page.text or "" for page in pages)
    clean = normalize(full_text)

    radications = extract_radications(full_text)
    if len(radications) > 1:
        findings.append({
            "Documento": document,
            "Página": "Varias",
            "Posible error": ERROR_RULES[0]["name"],
            "Categoría": ERROR_RULES[0]["category"],
            "Norma posible": ERROR_RULES[0]["norm"],
            "Evidencia": " / ".join(radications),
            "Explicación": (
                "Puede existir mezcla de expedientes o una cita válida. "
                "Debe verificarse la carátula y el contexto."
            ),
            "Severidad": "Alta",
        })

    future_dates = [d for d in extract_dates(full_text) if d > date.today()]
    if future_dates:
        findings.append({
            "Documento": document,
            "Página": "Varias",
            "Posible error": ERROR_RULES[1]["name"],
            "Categoría": ERROR_RULES[1]["category"],
            "Norma posible": ERROR_RULES[1]["norm"],
            "Evidencia": ", ".join(d.strftime("%d/%m/%Y") for d in future_dates),
            "Explicación": "La fecha puede ser programada o un error material.",
            "Severidad": "Media",
        })

    technical = []
    for token in ("phonak sky", "phonak naida", "lumity", "l90-up", "up l90"):
        if token in clean:
            technical.append(token)

    if len(set(technical)) >= 2:
        findings.append({
            "Documento": document,
            "Página": "Varias",
            "Posible error": ERROR_RULES[2]["name"],
            "Categoría": ERROR_RULES[2]["category"],
            "Norma posible": ERROR_RULES[2]["norm"],
            "Evidencia": " / ".join(sorted(set(technical))),
            "Explicación": (
                "Los documentos mencionan referencias diferentes. "
                "Debe compararse prescripción, fallo, autorización y entrega."
            ),
            "Severidad": "Alta",
        })

    if any(x in clean for x in ("no obra prueba", "no se acredito", "no se aporto")):
        if any(x in clean for x in ("anexo", "historia clinica", "constancia", "dictamen")):
            findings.append({
                "Documento": document,
                "Página": "Varias",
                "Posible error": ERROR_RULES[3]["name"],
                "Categoría": ERROR_RULES[3]["category"],
                "Norma posible": ERROR_RULES[3]["norm"],
                "Evidencia": "El texto niega prueba y también menciona anexos o soportes.",
                "Explicación": "Debe comprobarse si la prueba fue aportada y valorada.",
                "Severidad": "Alta",
            })

    return findings


def detect_conducts(document: str, pages: list[PageTrace]) -> list[dict]:
    rows = []
    full_text = "\n".join(page.text or "" for page in pages)
    clean = normalize(full_text)

    for rule in CONDUCTS:
        hits = [term for term in rule["terms"] if term in clean]
        if not hits:
            continue

        fragments = [
            item.strip()
            for item in re.split(r"(?<=[.;:])\s+|\n+", full_text)
            if any(term in normalize(item) for term in hits)
        ]

        rows.append({
            "Documento": document,
            "Posible conducta relevante": rule["name"],
            "Coincidencias": " | ".join(hits),
            "Fragmento principal": fragments[0] if fragments else "",
            "Norma o marco posible": rule["norm"],
            "Utilidad para vigilancia": rule["purpose"],
            "Conclusión": (
                "Indicio que debe verificarse con cronología, constancias "
                "y estado actual del proceso."
            ),
        })

    return rows


def answer_question(question: str, pages: list[PageTrace]) -> tuple[str, list[dict]]:
    clean_question = normalize(question)
    keywords = {
        word
        for word in re.findall(r"\b[a-z0-9]{4,}\b", clean_question)
        if word not in {
            "para", "como", "cual", "cuando", "donde", "esta",
            "este", "esto", "debe", "puede", "tiene", "hacer",
        }
    }

    candidates = []

    for page in pages:
        fragments = [
            item.strip()
            for item in re.split(r"(?<=[.;:])\s+|\n+", page.text or "")
            if len(item.strip()) >= 25
        ]

        for fragment in fragments:
            clean_fragment = normalize(fragment)
            score = sum(word in clean_fragment for word in keywords)
            if score:
                candidates.append({
                    "Documento": page.document,
                    "Página": page.page,
                    "Fragmento": fragment,
                    "Coincidencias": score,
                })

    candidates.sort(key=lambda item: item["Coincidencias"], reverse=True)
    top = candidates[:5]

    if not top:
        return (
            "No encontré en los documentos un fragmento suficiente para responder "
            "esa pregunta. Revisa el texto de la pregunta o carga más piezas del expediente.",
            [],
        )

    evidence_text = " ".join(item["Fragmento"] for item in top[:3])
    answer = (
        "Con base en los fragmentos más relacionados, el expediente indica lo siguiente: "
        + evidence_text
        + " Esta respuesta debe revisarse junto con el documento completo y no debe "
          "interpretarse como una conclusión jurídica definitiva."
    )

    return answer, top


with st.sidebar:
    st.header("OCR")
    enabled = st.checkbox("Aplicar OCR", value=True)
    min_chars = st.slider("Mínimo de caracteres útiles", 20, 300, 80, 10)
    max_pages = st.slider("Máximo de páginas OCR", 5, 150, 50, 5)
    dpi = st.select_slider("Resolución OCR", [150, 200, 220, 250, 300], value=220)


uploaded_files = st.file_uploader(
    "Carga uno o varios documentos del expediente",
    type=["pdf", "docx", "txt", "jpg", "jpeg", "png", "eml"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.stop()


all_pages = []
documents = {}

with st.spinner("Leyendo y organizando documentos..."):
    for uploaded in uploaded_files:
        raw = cached_load(
            uploaded.name,
            digest(uploaded.getvalue()),
            uploaded.getvalue(),
            enabled,
            min_chars,
            max_pages,
            dpi,
        )
        pages = [restore(item) for item in raw]
        documents[uploaded.name] = pages
        all_pages.extend(pages)


st.subheader("1. Formular una pregunta y obtener respuesta")

question = st.text_area(
    "Pregunta sobre el expediente",
    placeholder=(
        "Ejemplo: ¿El juzgado dejó vencer el término sin decidir? "
        "¿Qué actuación está pendiente? ¿Existe prueba de notificación?"
    ),
    height=100,
)

if question.strip():
    answer, evidence = answer_question(question, all_pages)
    st.info(answer)

    if evidence:
        st.markdown("#### Fragmentos usados para responder")
        st.dataframe(
            pd.DataFrame(evidence),
            use_container_width=True,
            hide_index=True,
        )


st.subheader("2. Conteo automático de términos")

term_rows = []
for document, pages in documents.items():
    term_rows.extend(detect_terms(document, pages))

terms_df = pd.DataFrame(term_rows)

if terms_df.empty:
    st.warning("No se detectaron términos expresos con las reglas actuales.")
else:
    st.dataframe(terms_df, use_container_width=True, hide_index=True)


st.subheader("3. Posibles errores encontrados")

error_rows = []
for document, pages in documents.items():
    error_rows.extend(detect_errors(document, pages))

errors_df = pd.DataFrame(error_rows)

if errors_df.empty:
    st.success(
        "No se detectaron errores claros con las reglas automáticas. "
        "Esto no demuestra que el expediente esté libre de errores."
    )
else:
    st.dataframe(errors_df, use_container_width=True, hide_index=True)


st.subheader("4. Conductas que podrían ameritar Vigilancia Judicial")

conduct_rows = []
for document, pages in documents.items():
    conduct_rows.extend(detect_conducts(document, pages))

conducts_df = pd.DataFrame(conduct_rows)

if conducts_df.empty:
    st.warning(
        "No se identificaron conductas claras relacionadas con mora o gestión. "
        "Puede faltar una actuación, constancia o consulta actual del proceso."
    )
else:
    st.dataframe(conducts_df, use_container_width=True, hide_index=True)


st.subheader("5. Semáforo integral")

risk = 0
risk += len(errors_df) * 15
risk += len(conducts_df) * 20

if not terms_df.empty and (terms_df["Estado"] == "Vencido").any():
    risk += 30

risk = min(100, risk)

if risk >= 65:
    st.error(
        f"🔴 REVISIÓN PRIORITARIA — {risk}/100. "
        "Hay términos vencidos, errores relevantes o conductas que deben comprobarse."
    )
elif risk >= 30:
    st.warning(
        f"🟡 REQUIERE COMPLETAR Y VERIFICAR — {risk}/100."
    )
else:
    st.success(
        f"🟢 SIN INDICIOS SUFICIENTES CON LOS DOCUMENTOS ACTUALES — {risk}/100."
    )


st.subheader("6. Exportar análisis")

output = io.BytesIO()

with pd.ExcelWriter(output, engine="openpyxl") as writer:
    terms_df.to_excel(writer, sheet_name="Términos", index=False)
    errors_df.to_excel(writer, sheet_name="Errores", index=False)
    conducts_df.to_excel(writer, sheet_name="Conductas vigilancia", index=False)

st.download_button(
    "Descargar revisión integral en Excel",
    data=output.getvalue(),
    file_name="revision_integral_vigilancia.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    type="primary",
)
