from __future__ import annotations

import hashlib
import io

import pandas as pd
import streamlit as st
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from legal_analyzer.document_loader import load_document
from legal_analyzer.models import PageTrace
from legal_analyzer.ocr_engine import OCRConfig, quality_label
from legal_analyzer.semaphore_engine import (
    build_semaphores,
    overall_semaphore,
)


st.set_page_config(
    page_title="Semáforo del Expediente",
    page_icon="🚦",
    layout="wide",
)

st.title("🚦 Semáforo del Expediente")
st.caption(
    "Identifica qué está controlado, qué debes revisar y qué requiere atención urgente."
)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@st.cache_data(show_spinner=False, max_entries=60)
def cached_load(
    name: str,
    content_hash: str,
    content: bytes,
    enabled: bool,
    min_chars: int,
    max_pages: int,
    dpi: int,
) -> list[dict]:
    del content_hash

    config = OCRConfig(
        enabled=enabled,
        min_useful_characters=min_chars,
        max_ocr_pages=max_pages,
        dpi=dpi,
    )

    return [
        trace.to_dict()
        for trace in load_document(name, content, config)
    ]


def restore(data: dict) -> PageTrace:
    return PageTrace(**data)


def badge(color: str) -> str:
    icons = {
        "Verde": "🟢",
        "Amarillo": "🟡",
        "Rojo": "🔴",
    }
    return f"{icons.get(color, '⚪')} {color}"


def create_word(items, overall) -> bytes:
    document = Document()
    document.styles["Normal"].font.name = "Arial"
    document.styles["Normal"].font.size = Pt(10)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("SEMÁFORO DEL EXPEDIENTE")
    run.bold = True
    run.font.size = Pt(15)

    document.add_paragraph(
        f"Estado general: {overall['label']} — "
        f"{overall['color']} — {overall['score']}/100"
    )

    for item in items:
        document.add_heading(
            f"{item.area} — {item.color}",
            level=1,
        )
        document.add_paragraph(
            f"Nivel de atención: {item.score}/100"
        )
        document.add_paragraph(
            f"Motivo: {item.reason}"
        )
        document.add_paragraph(
            f"Acción sugerida: {item.action}"
        )
        if item.source:
            document.add_paragraph(
                f"Fuentes: {item.source}"
            )

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


with st.sidebar:
    st.header("Lectura")
    ocr_enabled = st.checkbox("Aplicar OCR", value=True)
    min_chars = st.slider(
        "Mínimo de caracteres útiles",
        20,
        300,
        80,
        10,
    )
    max_pages = st.slider(
        "Máximo de páginas OCR",
        5,
        100,
        40,
        5,
    )
    dpi = st.select_slider(
        "Resolución OCR",
        [150, 200, 220, 250, 300],
        value=220,
    )


files = st.file_uploader(
    "Sube las piezas del expediente",
    type=["pdf", "docx", "txt", "jpg", "jpeg", "png", "eml"],
    accept_multiple_files=True,
)

if not files:
    st.info(
        "Carga el expediente para generar los semáforos."
    )
    st.stop()


documents: dict[str, list[PageTrace]] = {}
progress = st.progress(0)
message = st.empty()

for index, uploaded in enumerate(files):
    message.info(
        f"Evaluando {uploaded.name}"
    )

    content = uploaded.getvalue()

    try:
        raw = cached_load(
            uploaded.name,
            sha256(content),
            content,
            ocr_enabled,
            min_chars,
            max_pages,
            dpi,
        )

        documents[uploaded.name] = [
            restore(item)
            for item in raw
        ]

    except Exception as error:
        st.error(
            f"No se pudo procesar {uploaded.name}: {error}"
        )
        documents[uploaded.name] = []

    progress.progress(
        (index + 1) / len(files)
    )

message.empty()


quality_rows = []

for name, pages in documents.items():
    for page in pages:
        quality_rows.append(
            {
                "Documento": name,
                "Página": page.page,
                "Calidad": quality_label(page),
                "Método": page.extraction_method,
                "Confianza OCR": page.ocr_confidence,
            }
        )


items = build_semaphores(
    documents,
    quality_rows,
)

overall = overall_semaphore(
    items
)


st.subheader("1. Estado general")

col1, col2, col3 = st.columns([1.3, 1, 1])

with col1:
    st.metric(
        "Estado",
        overall["label"],
    )

with col2:
    st.metric(
        "Semáforo",
        badge(overall["color"]),
    )

with col3:
    st.metric(
        "Nivel de atención",
        f"{overall['score']}/100",
    )

st.progress(
    overall["score"] / 100
)

if overall["color"] == "Rojo":
    st.error(
        "Hay aspectos críticos que requieren atención prioritaria."
    )
elif overall["color"] == "Amarillo":
    st.warning(
        "El expediente tiene alertas que deben revisarse antes de actuar."
    )
else:
    st.success(
        "El expediente está razonablemente controlado con la información cargada."
    )


st.subheader("2. Semáforos por área")

columns = st.columns(3)

for index, item in enumerate(items):
    with columns[index % 3]:
        if item.color == "Rojo":
            st.error(
                f"### 🔴 {item.area}\n"
                f"**Atención:** {item.score}/100\n\n"
                f"**Qué cuidar:** {item.reason}\n\n"
                f"**Qué hacer:** {item.action}"
            )
        elif item.color == "Amarillo":
            st.warning(
                f"### 🟡 {item.area}\n"
                f"**Atención:** {item.score}/100\n\n"
                f"**Qué revisar:** {item.reason}\n\n"
                f"**Qué hacer:** {item.action}"
            )
        else:
            st.success(
                f"### 🟢 {item.area}\n"
                f"**Atención:** {item.score}/100\n\n"
                f"**Controlado:** {item.reason}\n\n"
                f"**Mantener:** {item.action}"
            )


st.subheader("3. Tabla de control")

table = pd.DataFrame(
    [
        {
            "Área": item.area,
            "Estado": badge(item.color),
            "Atención": item.score,
            "Qué debes cuidar": item.reason,
            "Acción sugerida": item.action,
            "Fuente": item.source,
            "Revisión humana": "",
        }
        for item in items
    ]
)

edited = st.data_editor(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Atención": st.column_config.ProgressColumn(
            "Atención",
            min_value=0,
            max_value=100,
            format="%d",
        ),
        "Revisión humana": st.column_config.TextColumn(
            "Revisión humana",
            width="large",
        ),
    },
    key="semaphore_table",
)


st.subheader("4. Prioridades")

red_items = [
    item
    for item in items
    if item.color == "Rojo"
]

yellow_items = [
    item
    for item in items
    if item.color == "Amarillo"
]

green_items = [
    item
    for item in items
    if item.color == "Verde"
]

tab1, tab2, tab3 = st.tabs(
    [
        f"🔴 Urgente ({len(red_items)})",
        f"🟡 Revisar ({len(yellow_items)})",
        f"🟢 Controlado ({len(green_items)})",
    ]
)

with tab1:
    if not red_items:
        st.success(
            "No hay alertas rojas con las reglas actuales."
        )
    for item in red_items:
        st.error(
            f"**{item.area}:** {item.action}"
        )

with tab2:
    if not yellow_items:
        st.success(
            "No hay alertas amarillas."
        )
    for item in yellow_items:
        st.warning(
            f"**{item.area}:** {item.action}"
        )

with tab3:
    if not green_items:
        st.info(
            "Todavía no hay áreas clasificadas como controladas."
        )
    for item in green_items:
        st.success(
            f"**{item.area}:** {item.reason}"
        )


st.subheader("5. Exportar reporte")

excel = io.BytesIO()

with pd.ExcelWriter(
    excel,
    engine="openpyxl",
) as writer:
    edited.to_excel(
        writer,
        sheet_name="Semaforo expediente",
        index=False,
    )
    pd.DataFrame(
        quality_rows
    ).to_excel(
        writer,
        sheet_name="Calidad documental",
        index=False,
    )

download1, download2 = st.columns(2)

with download1:
    st.download_button(
        "Descargar semáforo en Excel",
        data=excel.getvalue(),
        file_name="semaforo_expediente.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

with download2:
    st.download_button(
        "Descargar informe en Word",
        data=create_word(
            items,
            overall,
        ),
        file_name="informe_semaforo_expediente.docx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        use_container_width=True,
    )


st.warning(
    "Los colores son alertas preliminares. El término procesal, la suficiencia "
    "de la prueba y el cumplimiento deben confirmarse con el expediente original."
)
