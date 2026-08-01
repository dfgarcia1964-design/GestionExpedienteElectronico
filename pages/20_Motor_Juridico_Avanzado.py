from __future__ import annotations

import hashlib
import io

import pandas as pd
import streamlit as st

from legal_analyzer.advanced_legal_engine import analyze, answer_question
from legal_analyzer.document_loader import load_document
from legal_analyzer.models import PageTrace
from legal_analyzer.ocr_engine import OCRConfig


st.set_page_config(
    page_title="Motor Jurídico Avanzado",
    page_icon="🧠",
    layout="wide",
)

st.title("🧠 Motor Jurídico Avanzado")
st.caption(
    "Análisis cruzado de documentos, preguntas con evidencia, términos, "
    "errores, contradicciones y posibles conductas para Vigilancia Judicial."
)

st.error(
    "Este motor produce hallazgos preliminares. No declara responsabilidad, "
    "no sustituye recursos y no puede afirmar una violación sin verificación humana."
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@st.cache_data(show_spinner=False, max_entries=250)
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


with st.sidebar:
    st.header("OCR")
    enabled = st.checkbox("Aplicar OCR", value=True)
    min_chars = st.slider("Mínimo de caracteres útiles", 20, 300, 80, 10)
    max_pages = st.slider("Máximo de páginas OCR", 5, 200, 75, 5)
    dpi = st.select_slider(
        "Resolución OCR",
        [150, 200, 220, 250, 300],
        value=220,
    )


uploaded_files = st.file_uploader(
    "Carga uno o varios documentos del expediente",
    type=["pdf", "docx", "txt", "jpg", "jpeg", "png", "eml"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.stop()


pages = []
errors_loading = []

with st.spinner("Leyendo documentos y construyendo el análisis cruzado..."):
    for uploaded in uploaded_files:
        try:
            raw = cached_load(
                uploaded.name,
                digest(uploaded.getvalue()),
                uploaded.getvalue(),
                enabled,
                min_chars,
                max_pages,
                dpi,
            )
            pages.extend(restore(item) for item in raw)
        except Exception as error:
            errors_loading.append(f"{uploaded.name}: {error}")


if errors_loading:
    st.warning(
        "Algunos archivos no pudieron leerse completamente:\n\n"
        + "\n".join(errors_loading)
    )

if not pages:
    st.error("No se pudo obtener texto útil de los documentos.")
    st.stop()


result = analyze(pages)


st.subheader("1. Preguntar al expediente")

default_questions = [
    "¿Cuál es la última actuación y qué sigue pendiente?",
    "¿Existen términos vencidos?",
    "¿Hay contradicciones entre los documentos?",
    "¿Qué errores fácticos aparecen?",
    "¿Se omitió valorar alguna prueba relevante?",
    "¿La notificación está suficientemente acreditada?",
    "¿El despacho dejó una solicitud sin resolver?",
    "¿Hay señales de mora o inactividad?",
    "¿Se adoptaron medidas suficientes para cumplir la tutela?",
    "¿Hay elementos para preparar Vigilancia Judicial Administrativa?",
]

selected = st.selectbox(
    "Selecciona una pregunta importante",
    ["Escribir otra pregunta"] + default_questions,
)

question = (
    st.text_area("Escribe la pregunta", height=90)
    if selected == "Escribir otra pregunta"
    else selected
)

if st.button(
    "Responder con evidencia documental",
    type="primary",
    use_container_width=True,
):
    response = answer_question(question, pages)

    st.info(
        f"**Confianza preliminar: {response['Confianza']}%**\n\n"
        f"{response['Respuesta']}"
    )

    if response["Evidencia"]:
        st.dataframe(
            pd.DataFrame(response["Evidencia"]),
            use_container_width=True,
            hide_index=True,
        )


st.subheader("2. Semáforo integral avanzado")

color = result["color"]
score = result["score"]
icon = {"Rojo": "🔴", "Amarillo": "🟡", "Verde": "🟢"}[color]

if color == "Rojo":
    st.error(f"{icon} REVISIÓN PRIORITARIA — {score}/100")
elif color == "Amarillo":
    st.warning(f"{icon} REQUIERE COMPLETAR Y VERIFICAR — {score}/100")
else:
    st.success(f"{icon} SIN INDICIOS SUFICIENTES — {score}/100")

components = pd.DataFrame(
    [
        {"Componente": key, "Puntaje": value}
        for key, value in result["score_components"].items()
    ]
)

st.dataframe(
    components,
    use_container_width=True,
    hide_index=True,
)


st.subheader("3. Términos detectados")

terms_df = pd.DataFrame(result["terms"])

if terms_df.empty:
    st.warning("No se detectaron términos expresos.")
else:
    st.dataframe(terms_df, use_container_width=True, hide_index=True)


st.subheader("4. Contradicciones entre documentos")

contradictions_df = pd.DataFrame(result["contradictions"])

if contradictions_df.empty:
    st.success("No se detectaron contradicciones claras con las reglas actuales.")
else:
    st.dataframe(
        contradictions_df,
        use_container_width=True,
        hide_index=True,
    )

    for index, row in contradictions_df.iterrows():
        with st.expander(
            f"Contradicción {index + 1}: {row['Tema']}",
            expanded=index == 0,
        ):
            st.markdown(
                f"**Documento 1:** {row['Documento versión 1']}, "
                f"página {row['Página versión 1']}"
            )
            st.markdown(f"**Versión 1:** {row['Versión 1']}")
            st.markdown(
                f"**Documento 2:** {row['Documento versión 2']}, "
                f"página {row['Página versión 2']}"
            )
            st.markdown(f"**Versión 2:** {row['Versión 2']}")
            st.warning(row["Qué debe revisarse"])


st.subheader("5. Posibles errores")

errors_df = pd.DataFrame(result["errors"])

if errors_df.empty:
    st.success("No se detectaron errores claros con las reglas actuales.")
else:
    st.dataframe(errors_df, use_container_width=True, hide_index=True)


st.subheader("6. Conductas relevantes para Vigilancia Judicial")

conducts_df = pd.DataFrame(result["conducts"])

if conducts_df.empty:
    st.warning("No se detectaron conductas claras con las reglas actuales.")
else:
    st.dataframe(conducts_df, use_container_width=True, hide_index=True)


st.subheader("7. Conclusión y actuación sugerida")

if color == "Rojo":
    conclusion = (
        "El expediente requiere revisión prioritaria. Antes de radicar, confirma "
        "la fecha real de notificación, el vencimiento de los términos, la actuación "
        "concreta pendiente, las contradicciones y el estado actual del proceso."
    )
elif color == "Amarillo":
    conclusion = (
        "Hay indicios útiles, pero faltan verificaciones o soportes. Completa la "
        "cronología y las constancias antes de presentar la solicitud."
    )
else:
    conclusion = (
        "Con los documentos actuales no aparecen elementos suficientes para recomendar "
        "una Vigilancia Judicial."
    )

st.info(conclusion)


st.subheader("8. Exportar análisis")

output = io.BytesIO()

with pd.ExcelWriter(output, engine="openpyxl") as writer:
    components.to_excel(writer, sheet_name="Puntaje", index=False)
    terms_df.to_excel(writer, sheet_name="Términos", index=False)
    contradictions_df.to_excel(writer, sheet_name="Contradicciones", index=False)
    errors_df.to_excel(writer, sheet_name="Errores", index=False)
    conducts_df.to_excel(writer, sheet_name="Conductas", index=False)

st.download_button(
    "Descargar análisis avanzado en Excel",
    data=output.getvalue(),
    file_name="motor_juridico_avanzado.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    type="primary",
)
