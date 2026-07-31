import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st
from PyPDF2 import PdfReader


st.set_page_config(
    page_title="Analizador Jurídico",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Analizador jurídico de expedientes")
st.caption(
    "Primera versión: extrae texto, clasifica documentos y genera "
    "una línea de tiempo preliminar."
)

TIPOS_DOCUMENTO = {
    "Derecho de petición": [
        "derecho de petición",
        "ley 1755",
        "petición respetuosa",
    ],
    "Acción de tutela": [
        "acción de tutela",
        "solicitud de amparo",
        "derechos fundamentales",
    ],
    "Auto admisorio": [
        "auto admisorio",
        "admite la acción de tutela",
        "admitir la presente acción",
    ],
    "Contestación": [
        "contestación",
        "respuesta a la acción de tutela",
        "informe rendido",
    ],
    "Fallo de tutela": [
        "fallo de tutela",
        "resuelve",
        "amparar",
        "negar el amparo",
    ],
    "Impugnación": [
        "impugnación",
        "impugnar el fallo",
    ],
    "Incidente de desacato": [
        "incidente de desacato",
        "desacato",
        "incumplimiento del fallo",
    ],
    "Auto de requerimiento": [
        "requerir",
        "auto de requerimiento",
        "requiérase",
    ],
    "Notificación": [
        "notificación",
        "constancia de envío",
        "correo electrónico",
    ],
}


def extraer_texto_pdf(contenido: bytes) -> tuple[str, int]:
    lector = PdfReader(io.BytesIO(contenido))
    paginas = []

    for pagina in lector.pages:
        paginas.append(pagina.extract_text() or "")

    return "\n".join(paginas), len(lector.pages)


def clasificar_documento(texto: str) -> tuple[str, int]:
    texto_normalizado = texto.lower()
    mejor_tipo = "Documento no clasificado"
    mejor_puntaje = 0

    for tipo, palabras in TIPOS_DOCUMENTO.items():
        puntaje = sum(
            1 for palabra in palabras
            if palabra in texto_normalizado
        )

        if puntaje > mejor_puntaje:
            mejor_tipo = tipo
            mejor_puntaje = puntaje

    return mejor_tipo, mejor_puntaje


def buscar_fecha(texto: str) -> Optional[str]:
    patrones = [
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
        (
            r"\b(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})"
        ),
    ]

    coincidencia = re.search(patrones[0], texto, re.IGNORECASE)

    if coincidencia:
        dia, mes, anio = coincidencia.groups()

        try:
            fecha = datetime(int(anio), int(mes), int(dia))
            return fecha.strftime("%Y-%m-%d")
        except ValueError:
            pass

    coincidencia = re.search(patrones[1], texto, re.IGNORECASE)

    if coincidencia:
        meses = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }

        dia, mes_texto, anio = coincidencia.groups()

        try:
            fecha = datetime(
                int(anio),
                meses[mes_texto.lower()],
                int(dia),
            )
            return fecha.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def crear_resumen(texto: str, limite: int = 700) -> str:
    texto_limpio = re.sub(r"\s+", " ", texto).strip()

    if not texto_limpio:
        return "No fue posible extraer texto."

    return texto_limpio[:limite] + (
        "..." if len(texto_limpio) > limite else ""
    )


archivos = st.file_uploader(
    "Sube las piezas procesales en formato PDF",
    type=["pdf"],
    accept_multiple_files=True,
)

if archivos:
    resultados = []

    barra = st.progress(0)

    for indice, archivo in enumerate(archivos):
        try:
            contenido = archivo.getvalue()
            texto, paginas = extraer_texto_pdf(contenido)
            tipo, puntaje = clasificar_documento(texto)
            fecha = buscar_fecha(texto)

            resultados.append(
                {
                    "Fecha detectada": fecha,
                    "Documento": archivo.name,
                    "Tipo procesal": tipo,
                    "Confianza básica": puntaje,
                    "Páginas": paginas,
                    "Texto extraído": len(texto),
                    "Resumen preliminar": crear_resumen(texto),
                }
            )

        except Exception as error:
            resultados.append(
                {
                    "Fecha detectada": None,
                    "Documento": archivo.name,
                    "Tipo procesal": "Error de lectura",
                    "Confianza básica": 0,
                    "Páginas": 0,
                    "Texto extraído": 0,
                    "Resumen preliminar": str(error),
                }
            )

        barra.progress((indice + 1) / len(archivos))

    tabla = pd.DataFrame(resultados)

    tabla["_orden"] = pd.to_datetime(
        tabla["Fecha detectada"],
        errors="coerce",
    )

    tabla = tabla.sort_values(
        by=["_orden", "Documento"],
        na_position="last",
    ).drop(columns=["_orden"])

    st.success(f"Se procesaron {len(tabla)} documentos.")

    st.subheader("Línea de tiempo preliminar")

    st.dataframe(
        tabla[
            [
                "Fecha detectada",
                "Documento",
                "Tipo procesal",
                "Confianza básica",
                "Páginas",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Resumen de las piezas")

    for _, fila in tabla.iterrows():
        with st.expander(
            f"{fila['Tipo procesal']} — {fila['Documento']}"
        ):
            st.write(f"**Fecha detectada:** {fila['Fecha detectada'] or 'No detectada'}")
            st.write(f"**Número de páginas:** {fila['Páginas']}")
            st.write(f"**Resumen preliminar:** {fila['Resumen preliminar']}")

    archivo_excel = io.BytesIO()

    with pd.ExcelWriter(archivo_excel, engine="openpyxl") as escritor:
        tabla.to_excel(
            escritor,
            sheet_name="Analisis preliminar",
            index=False,
        )

    st.download_button(
        "Descargar análisis preliminar en Excel",
        data=archivo_excel.getvalue(),
        file_name="analisis_preliminar_expediente.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    st.warning(
        "Este resultado es preliminar. No reemplaza la revisión jurídica "
        "ni confirma por sí solo el cumplimiento de términos u órdenes."
    )
else:
    st.info(
        "Carga varios PDF del mismo proceso para construir la línea de tiempo."
    )
