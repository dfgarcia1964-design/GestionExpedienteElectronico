from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from legal_analyzer.document_loader import load_document
from legal_analyzer.models import PageTrace
from legal_analyzer.ocr_engine import OCRConfig


st.set_page_config(
    page_title="Organizador Vigilancia Judicial",
    page_icon="📚",
    layout="wide",
)

st.title("📚 Organizador Automático de Vigilancia Judicial")
st.caption(
    "Clasifica documentos, detecta faltantes, organiza anexos, construye cronología "
    "y genera un paquete listo para revisar antes de radicar."
)

st.error(
    "La organización es automática y preliminar. Antes de radicar, comprueba "
    "nombres, fechas, radicado, notificaciones y contenido de cada anexo."
)


CATEGORIES = {
    "A": {
        "name": "Identificación del proceso",
        "keywords": (
            "caratula", "consulta proceso", "expediente", "radicado",
            "documento identidad", "cedula",
        ),
    },
    "B": {
        "name": "Orden judicial y fallo",
        "keywords": (
            "fallo de tutela", "sentencia", "parte resolutiva",
            "orden judicial", "resuelve",
        ),
    },
    "C": {
        "name": "Notificación e inicio del término",
        "keywords": (
            "notificacion", "acuse", "ejecutoria", "correo enviado",
            "entrega del mensaje", "mensaje de datos",
        ),
    },
    "D": {
        "name": "Actuaciones del despacho",
        "keywords": (
            "auto de sustanciacion", "auto interlocutorio", "providencia",
            "juzgado", "tribunal", "secretaria",
        ),
    },
    "E": {
        "name": "Memoriales del accionante",
        "keywords": (
            "memorial", "incidente de desacato", "solicitud de impulso",
            "solicitud de decision", "accionante solicita",
        ),
    },
    "F": {
        "name": "Constancias de recepción",
        "keywords": (
            "recibido", "radicacion", "acuse de recibo", "sello",
            "confirmacion de recepcion",
        ),
    },
    "G": {
        "name": "Consulta actualizada del expediente",
        "keywords": (
            "consulta de procesos", "historial de actuaciones",
            "ultima actuacion", "estado del proceso", "paso al despacho",
        ),
    },
    "H": {
        "name": "Respuestas de entidades",
        "keywords": (
            "respuesta sanitas", "respuesta audiocom", "respuesta entidad",
            "informe de cumplimiento", "autorizacion",
        ),
    },
    "I": {
        "name": "Prueba de incumplimiento material",
        "keywords": (
            "orden medica", "historia clinica", "acta de entrega",
            "ficha tecnica", "concepto medico", "prescripcion",
        ),
    },
    "J": {
        "name": "Errores documentales",
        "keywords": (
            "matriz de errores", "comparacion fallo", "error factico",
            "incongruencia", "solicitud de correccion",
        ),
    },
    "K": {
        "name": "Conteo de términos",
        "keywords": (
            "conteo de terminos", "termino vencido", "dias habiles",
            "calendario judicial", "vencimiento",
        ),
    },
    "L": {
        "name": "Cronología general",
        "keywords": (
            "cronologia", "linea de tiempo", "secuencia de actuaciones",
        ),
    },
    "M": {
        "name": "Actuación pendiente",
        "keywords": (
            "solicitud no resuelta", "actuacion pendiente",
            "certificacion de no decision", "sin resolver",
        ),
    },
}

ESSENTIALS = [
    ("Fallo o providencia principal", ("fallo de tutela", "sentencia", "resuelve")),
    ("Radicado completo", ("expediente", "radicado")),
    ("Constancia de notificación", ("notificacion", "acuse", "ejecutoria")),
    ("Memorial o solicitud pendiente", ("memorial", "solicitud", "incidente de desacato")),
    ("Constancia de recepción", ("recibido", "radicacion", "acuse de recibo")),
    ("Consulta actualizada", ("consulta de procesos", "ultima actuacion", "estado del proceso")),
    ("Prueba del término o demora", ("termino", "vencimiento", "dias habiles", "horas")),
]


def normalize(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        (text or "").translate(
            str.maketrans(
                "áéíóúüñÁÉÍÓÚÜÑ",
                "aeiouunAEIOUUN",
            )
        ).lower(),
    ).strip()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@st.cache_data(show_spinner=False, max_entries=400)
def cached_load(name, content_hash, content, enabled, min_chars, max_pages, dpi):
    del content_hash

    config = OCRConfig(
        enabled=enabled,
        min_useful_characters=min_chars,
        max_ocr_pages=max_pages,
        dpi=dpi,
    )

    return [
        item.to_dict()
        for item in load_document(name, content, config)
    ]


def restore(data: dict) -> PageTrace:
    return PageTrace(**data)


def extract_dates(text: str) -> list[date]:
    values = []

    for day, month, year in re.findall(
        r"\b([0-3]?\d)[/-]([01]?\d)[/-]((?:19|20)\d{2})\b",
        text or "",
    ):
        try:
            values.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass

    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }

    clean = normalize(text)
    pattern = (
        r"\b([0-3]?\d)\s+de\s+("
        + "|".join(months)
        + r")\s+de\s+((?:19|20)\d{2})\b"
    )

    for day, month_name, year in re.findall(pattern, clean):
        try:
            values.append(date(int(year), months[month_name], int(day)))
        except ValueError:
            pass

    return list(dict.fromkeys(values))


def extract_radications(text: str) -> list[str]:
    values = []

    for pattern in (
        r"\b\d{2}-\d{3}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}\b",
        r"\b\d{23}\b",
        r"\b20\d{2}-\d{5}\b",
    ):
        values.extend(re.findall(pattern, text or ""))

    return list(dict.fromkeys(values))


def classify_document(name: str, text: str) -> tuple[str, int, str]:
    combined = normalize(name + " " + text)
    scores = {}

    for code, info in CATEGORIES.items():
        hits = [
            keyword
            for keyword in info["keywords"]
            if normalize(keyword) in combined
        ]
        scores[code] = len(hits)

    best_code = max(scores, key=scores.get)
    best_score = scores[best_code]

    if best_score == 0:
        return "A", 20, "Clasificación provisional por falta de coincidencias."

    confidence = min(95, 45 + best_score * 12)

    matched = [
        keyword
        for keyword in CATEGORIES[best_code]["keywords"]
        if normalize(keyword) in combined
    ]

    return (
        best_code,
        confidence,
        "Coincidencias: " + ", ".join(matched[:6]),
    )


def build_index_pdf(rows: list[dict], metadata: dict) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = [
        Paragraph("ÍNDICE DE ANEXOS — VIGILANCIA JUDICIAL ADMINISTRATIVA", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(
            f"<b>Radicado:</b> {metadata.get('radicado') or 'Por completar'}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Despacho:</b> {metadata.get('despacho') or 'Por completar'}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Solicitante:</b> {metadata.get('solicitante') or 'Por completar'}",
            styles["BodyText"],
        ),
        Spacer(1, 0.6 * cm),
    ]

    data = [["Código", "Categoría", "Archivo", "Fecha", "Descripción"]]

    for row in rows:
        data.append([
            row["Código final"],
            row["Categoría final"],
            row["Archivo original"],
            row["Fecha principal"],
            row["Descripción"],
        ])

    table = Table(
        data,
        colWidths=[2.0 * cm, 3.5 * cm, 5.0 * cm, 2.2 * cm, 5.0 * cm],
        repeatRows=1,
    )

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, None),
        ("BACKGROUND", (0, 0), (-1, 0), None),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]))

    story.append(table)
    doc.build(story)

    return buffer.getvalue()


def build_request_draft(metadata: dict, chronology: pd.DataFrame, missing: list[str]) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = [
        Paragraph("BORRADOR — SOLICITUD DE VIGILANCIA JUDICIAL ADMINISTRATIVA", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(
            f"<b>Solicitante:</b> {metadata.get('solicitante') or 'POR COMPLETAR'}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Despacho:</b> {metadata.get('despacho') or 'POR COMPLETAR'}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Radicado:</b> {metadata.get('radicado') or 'POR COMPLETAR'}",
            styles["BodyText"],
        ),
        Spacer(1, 0.5 * cm),
        Paragraph("<b>1. Objeto de la solicitud</b>", styles["Heading2"]),
        Paragraph(
            "Solicito verificar la oportunidad, eficacia y gestión administrativa "
            "del despacho respecto de las actuaciones pendientes identificadas en "
            "los documentos anexos, sin pretender que se modifique el contenido "
            "de ninguna providencia judicial.",
            styles["BodyText"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("<b>2. Cronología preliminar</b>", styles["Heading2"]),
    ]

    if chronology.empty:
        story.append(
            Paragraph(
                "No fue posible construir una cronología automática. Debe completarse manualmente.",
                styles["BodyText"],
            )
        )
    else:
        data = [["Fecha", "Documento", "Categoría"]]

        for _, row in chronology.iterrows():
            data.append([
                str(row["Fecha principal"]),
                str(row["Archivo original"]),
                str(row["Categoría final"]),
            ])

        table = Table(
            data,
            colWidths=[3 * cm, 8 * cm, 6 * cm],
            repeatRows=1,
        )

        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, None),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))

        story.append(table)

    story.extend([
        Spacer(1, 0.4 * cm),
        Paragraph("<b>3. Documentos pendientes</b>", styles["Heading2"]),
    ])

    if missing:
        for item in missing:
            story.append(Paragraph(f"• {item}", styles["BodyText"]))
    else:
        story.append(
            Paragraph(
                "No se detectaron faltantes esenciales en la revisión automática.",
                styles["BodyText"],
            )
        )

    story.extend([
        Spacer(1, 0.4 * cm),
        Paragraph("<b>4. Petición</b>", styles["Heading2"]),
        Paragraph(
            "Verificar la actuación administrativa del despacho, determinar el estado "
            "actual del proceso y establecer si existe demora o falta de gestión respecto "
            "de la actuación pendiente.",
            styles["BodyText"],
        ),
        Spacer(1, 1 * cm),
        Paragraph("Firma: ______________________________", styles["BodyText"]),
    ])

    doc.build(story)

    return buffer.getvalue()


def merge_pdf_files(index_pdf: bytes, classified_rows: list[dict], raw_files: dict[str, bytes]) -> bytes:
    writer = PdfWriter()
    index_reader = PdfReader(io.BytesIO(index_pdf))

    for page in index_reader.pages:
        writer.add_page(page)

    for row in classified_rows:
        name = row["Archivo original"]
        raw = raw_files.get(name)

        if not raw or not name.lower().endswith(".pdf"):
            continue

        try:
            reader = PdfReader(io.BytesIO(raw))

            for page in reader.pages:
                writer.add_page(page)
        except Exception:
            continue

    output = io.BytesIO()
    writer.write(output)

    return output.getvalue()


with st.sidebar:
    st.header("OCR")
    enabled = st.checkbox("Aplicar OCR", value=True)
    min_chars = st.slider("Mínimo de caracteres útiles", 20, 300, 80, 10)
    max_pages = st.slider("Máximo de páginas OCR", 5, 250, 100, 5)
    dpi = st.select_slider(
        "Resolución OCR",
        [150, 200, 220, 250, 300],
        value=220,
    )


st.subheader("1. Datos básicos")

c1, c2 = st.columns(2)

with c1:
    solicitante = st.text_input("Nombre del solicitante")
    despacho = st.text_input("Despacho judicial")

with c2:
    radicado_manual = st.text_input("Radicado completo")
    tipo_proceso = st.text_input("Tipo de proceso", value="Vigilancia Judicial Administrativa")


st.subheader("2. Cargar documentos")

uploaded_files = st.file_uploader(
    "Carga todos los documentos disponibles",
    type=["pdf", "docx", "txt", "jpg", "jpeg", "png", "eml"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.stop()


raw_files = {}
rows = []
all_text = ""

with st.spinner("Leyendo, clasificando y organizando documentos..."):
    for uploaded in uploaded_files:
        raw = uploaded.getvalue()
        raw_files[uploaded.name] = raw

        try:
            parsed = cached_load(
                uploaded.name,
                digest(raw),
                raw,
                enabled,
                min_chars,
                max_pages,
                dpi,
            )

            pages = [
                restore(item)
                for item in parsed
            ]

            text = "\n".join(
                page.text or ""
                for page in pages
            )
        except Exception as error:
            text = ""
            st.warning(
                f"No fue posible leer completamente {uploaded.name}: {error}"
            )

        all_text += "\n" + text

        code, confidence, reason = classify_document(
            uploaded.name,
            text,
        )

        dates = extract_dates(text)
        primary_date = min(dates) if dates else None

        rows.append({
            "Archivo original": uploaded.name,
            "Código sugerido": code,
            "Categoría sugerida": CATEGORIES[code]["name"],
            "Confianza": confidence,
            "Razón": reason,
            "Fecha principal": primary_date,
            "Descripción": "",
            "Código final": code,
            "Categoría final": CATEGORIES[code]["name"],
            "Incluir": True,
        })


detected_radications = extract_radications(all_text)

if not radicado_manual and detected_radications:
    radicado = detected_radications[0]
else:
    radicado = radicado_manual


st.subheader("3. Revisar clasificación")

classification_df = pd.DataFrame(rows)

edited = st.data_editor(
    classification_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Código final": st.column_config.SelectboxColumn(
            "Código final",
            options=list(CATEGORIES.keys()),
        ),
        "Categoría final": st.column_config.SelectboxColumn(
            "Categoría final",
            options=[
                info["name"]
                for info in CATEGORIES.values()
            ],
        ),
        "Incluir": st.column_config.CheckboxColumn("Incluir"),
        "Descripción": st.column_config.TextColumn(
            "Descripción",
            width="large",
        ),
        "Confianza": st.column_config.ProgressColumn(
            "Confianza",
            min_value=0,
            max_value=100,
            format="%d",
        ),
    },
    disabled=[
        "Archivo original",
        "Código sugerido",
        "Categoría sugerida",
        "Confianza",
        "Razón",
        "Fecha principal",
    ],
    key="vigilancia_file_classification",
)


selected_rows = edited[edited["Incluir"] == True].copy()

selected_rows = selected_rows.sort_values(
    by=["Código final", "Fecha principal", "Archivo original"],
    na_position="last",
).reset_index(drop=True)

sequence_by_code = {}

final_rows = []

for _, row in selected_rows.iterrows():
    code = row["Código final"]
    sequence_by_code[code] = sequence_by_code.get(code, 0) + 1
    sequence = sequence_by_code[code]

    row_dict = row.to_dict()
    row_dict["Código final"] = f"{code}{sequence:02d}"
    final_rows.append(row_dict)


final_df = pd.DataFrame(final_rows)


st.subheader("4. Verificación de documentos esenciales")

combined_normalized = normalize(
    " ".join(
        str(value)
        for value in final_df["Archivo original"].tolist()
    )
    + " "
    + all_text
)

essential_rows = []
missing = []

for essential, keywords in ESSENTIALS:
    found = any(
        normalize(keyword) in combined_normalized
        for keyword in keywords
    )

    essential_rows.append({
        "Documento esencial": essential,
        "Estado": "Encontrado" if found else "Faltante",
        "Acción": (
            "Revisar que sea legible y completo."
            if found
            else "Solicitar y cargar antes de radicar."
        ),
    })

    if not found:
        missing.append(essential)


essential_df = pd.DataFrame(essential_rows)

st.dataframe(
    essential_df,
    use_container_width=True,
    hide_index=True,
)

if missing:
    st.error(
        f"🔴 Faltan {len(missing)} documento(s) esencial(es)."
    )
else:
    st.success(
        "🟢 Se identificaron todos los grupos documentales esenciales."
    )


st.subheader("5. Cronología automática")

chronology_df = final_df[
    final_df["Fecha principal"].notna()
].copy()

chronology_df = chronology_df.sort_values(
    by="Fecha principal"
)

if chronology_df.empty:
    st.warning(
        "No se detectaron fechas suficientes para construir la cronología."
    )
else:
    st.dataframe(
        chronology_df[
            [
                "Fecha principal",
                "Código final",
                "Archivo original",
                "Categoría final",
                "Descripción",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


st.subheader("6. Vista final de anexos")

st.dataframe(
    final_df[
        [
            "Código final",
            "Categoría final",
            "Archivo original",
            "Fecha principal",
            "Descripción",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)


metadata = {
    "solicitante": solicitante,
    "despacho": despacho,
    "radicado": radicado,
    "tipo_proceso": tipo_proceso,
}


st.subheader("7. Generar paquete automático")

index_pdf = build_index_pdf(
    final_rows,
    metadata,
)

request_pdf = build_request_draft(
    metadata,
    chronology_df,
    missing,
)

annex_pdf = merge_pdf_files(
    index_pdf,
    final_rows,
    raw_files,
)


excel_buffer = io.BytesIO()

with pd.ExcelWriter(
    excel_buffer,
    engine="openpyxl",
) as writer:
    final_df.to_excel(
        writer,
        sheet_name="Índice anexos",
        index=False,
    )

    essential_df.to_excel(
        writer,
        sheet_name="Documentos esenciales",
        index=False,
    )

    chronology_df.to_excel(
        writer,
        sheet_name="Cronología",
        index=False,
    )


zip_buffer = io.BytesIO()

with zipfile.ZipFile(
    zip_buffer,
    "w",
    compression=zipfile.ZIP_DEFLATED,
) as package:
    package.writestr(
        "01_SOLICITUD_VIGILANCIA_BORRADOR.pdf",
        request_pdf,
    )

    package.writestr(
        "02_ANEXOS_VIGILANCIA.pdf",
        annex_pdf,
    )

    package.writestr(
        "03_INDICE_Y_CRONOLOGIA.xlsx",
        excel_buffer.getvalue(),
    )

    for row in final_rows:
        original_name = row["Archivo original"]
        raw = raw_files.get(original_name)

        if not raw:
            continue

        suffix = Path(original_name).suffix
        safe_name = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            Path(original_name).stem,
        )

        organized_name = (
            f"DOCUMENTOS_ORGANIZADOS/"
            f"{row['Código final']}_{safe_name}{suffix}"
        )

        package.writestr(
            organized_name,
            raw,
        )


st.download_button(
    "Descargar solicitud borrador",
    data=request_pdf,
    file_name="01_SOLICITUD_VIGILANCIA_BORRADOR.pdf",
    mime="application/pdf",
    use_container_width=True,
)

st.download_button(
    "Descargar anexos organizados",
    data=annex_pdf,
    file_name="02_ANEXOS_VIGILANCIA.pdf",
    mime="application/pdf",
    use_container_width=True,
)

st.download_button(
    "Descargar índice y cronología",
    data=excel_buffer.getvalue(),
    file_name="03_INDICE_Y_CRONOLOGIA.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.download_button(
    "Descargar paquete completo organizado",
    data=zip_buffer.getvalue(),
    file_name="PAQUETE_VIGILANCIA_JUDICIAL.zip",
    mime="application/zip",
    use_container_width=True,
    type="primary",
)


st.subheader("8. Resultado")

if missing:
    st.warning(
        "El paquete fue generado, pero todavía no está listo para radicar. "
        "Carga los documentos faltantes y vuelve a generarlo."
    )
else:
    st.success(
        "El paquete contiene solicitud borrador, anexos, índice, cronología "
        "y copias organizadas de los documentos."
    )
