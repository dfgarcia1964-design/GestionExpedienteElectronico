from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from legal_ui.despacho_store import DATA_DIR

NORMAS_DIR = DATA_DIR / "colombia_normas"
CONSTITUCION_JSON = NORMAS_DIR / "constitucion.json"
CONSTITUCION_FUENTE = NORMAS_DIR / "constitucion_fuente.txt"
ILEY_URL = "https://iley.fusense.com/"

NORMAS_CATALOGO = [
    {
        "id": "cp1991",
        "nombre": "Constitución Política de Colombia",
        "anio": 1991,
        "tipo": "Constitución",
    },
    {
        "id": "decreto2591",
        "nombre": "Decreto 2591 de 1991 — Acción de tutela",
        "anio": 1991,
        "tipo": "Decreto",
    },
    {
        "id": "ley1755",
        "nombre": "Ley 1755 de 2015 — Derecho de petición",
        "anio": 2015,
        "tipo": "Ley",
    },
]

EMBEDDED_NORMAS: dict[str, dict] = {
    "decreto2591": {
        "id": "decreto2591",
        "nombre": "Decreto 2591 de 1991 — Acción de tutela",
        "anio": 1991,
        "articulos": [
            {
                "numero": 1,
                "seccion": "Disposiciones generales",
                "texto": (
                    "Toda persona tendrá acción de tutela para reclamar ante los jueces, "
                    "en todo momento y lugar, mediante un procedimiento preferente y sumario, "
                    "por sí misma o por quien actúe a su nombre, la protección inmediata de sus "
                    "derechos constitucionales fundamentales, cuando quiera que éstos resulten "
                    "vulnerados o amenazados por la acción o la omisión de cualquier autoridad pública."
                ),
            },
            {
                "numero": 6,
                "seccion": "Procedimiento",
                "texto": (
                    "La acción de tutela procede contra toda acción u omisión de las autoridades "
                    "públicas, que haya violado, viole o amenace violar cualquiera de los derechos "
                    "de que trata el artículo 2 de esta ley. También procede contra acciones u "
                    "omisiones de particulares, de conformidad con lo establecido en el Capítulo III."
                ),
            },
            {
                "numero": 14,
                "seccion": "Términos",
                "texto": (
                    "En caso de urgencia, el juez podrá disponer medidas provisionales "
                    "indispensables para proteger los derechos fundamentales. El fallo de tutela "
                    "deberá proferirse dentro de los diez días siguientes a la presentación de la solicitud."
                ),
            },
        ],
    },
    "ley1755": {
        "id": "ley1755",
        "nombre": "Ley 1755 de 2015 — Derecho de petición",
        "anio": 2015,
        "articulos": [
            {
                "numero": 13,
                "seccion": "Derecho de petición",
                "texto": (
                    "Toda persona tiene derecho a presentar peticiones respetuosas a las autoridades "
                    "por motivos de interés general o particular, y a obtener pronta resolución "
                    "completa y de fondo sobre la misma."
                ),
            },
            {
                "numero": 14,
                "seccion": "Términos de respuesta",
                "texto": (
                    "Las peticiones de documentos y de información deberán resolverse dentro de "
                    "los diez (10) días siguientes a su recepción. Las demás peticiones deberán "
                    "resolverse dentro de los quince (15) días siguientes a su recepción."
                ),
            },
        ],
    },
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _clean(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _strip_references(text: str) -> str:
    for marker in ("Jurisprudencia Vigencia", "Leyes y Sentencias", "Ver la Constit"):
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
    text = re.sub(r"\(Ver [^)]+\)", "", text, flags=re.IGNORECASE)
    return _clean(text)


def _parse_constitution(raw: str) -> dict:
    start = raw.find("CONSTITUCI")
    if start < 0:
        raise ValueError("No se encontró la Constitución en la fuente local.")
    body = raw[start:]
    stop_markers = (
        "INSTRUMENTOS INTERNACIONALES",
        "INSTRUMENTOS INTERNACIONALES Y",
        "TRATADOS INTERNACIONALES",
    )
    for marker in stop_markers:
        idx = body.find(marker)
        if idx > 0:
            body = body[:idx]
            break

    parts = re.split(r"ART.{1,8}?CULO\s+(\d+)\.?\s*", body, flags=re.IGNORECASE)

    sections: list[dict] = []
    current_section = "Disposiciones generales"
    articles: list[dict] = []

    seen: set[int] = set()
    for idx in range(1, len(parts), 2):
        number = int(parts[idx])
        if number in seen:
            continue
        seen.add(number)
        chunk = _strip_references(parts[idx + 1])
        if not chunk:
            continue

        body_lines: list[str] = []
        for line in chunk.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            norm_line = _normalize(stripped)
            if (
                len(stripped) < 120
                and stripped == stripped.upper()
                and any(
                    word in norm_line
                    for word in ("titulo", "capitulo", "de los", "de las", "disposiciones")
                )
            ):
                current_section = stripped.title()
                continue
            body_lines.append(stripped)

        text = _clean(" ".join(body_lines))
        if not text:
            continue

        article = {
            "numero": number,
            "seccion": current_section,
            "texto": text,
            "norma": "Constitución Política de Colombia",
            "norma_id": "cp1991",
        }
        articles.append(article)

        if not sections or sections[-1]["nombre"] != current_section:
            sections.append({"nombre": current_section, "articulos": []})
        sections[-1]["articulos"].append(number)

    return {
        "id": "cp1991",
        "nombre": "Constitución Política de Colombia",
        "anio": 1991,
        "secciones": sections,
        "articulos": articles,
    }


def _ensure_constitution_json() -> dict:
    if CONSTITUCION_JSON.exists():
        return json.loads(CONSTITUCION_JSON.read_text(encoding="utf-8"))
    if not CONSTITUCION_FUENTE.exists():
        raise FileNotFoundError(
            "No hay corpus local. Coloque constitucion_fuente.txt en data/colombia_normas/ "
            "o ejecute _helpers/build_constitucion_corpus.py"
        )
    corpus = _parse_constitution(
        CONSTITUCION_FUENTE.read_text(encoding="utf-8", errors="replace")
    )
    NORMAS_DIR.mkdir(parents=True, exist_ok=True)
    CONSTITUCION_JSON.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return corpus


@lru_cache(maxsize=4)
def load_norma(norma_id: str) -> dict:
    if norma_id == "cp1991":
        return _ensure_constitution_json()
    if norma_id in EMBEDDED_NORMAS:
        return EMBEDDED_NORMAS[norma_id]
    raise KeyError(f"Norma no disponible: {norma_id}")


def list_normas() -> list[dict]:
    return NORMAS_CATALOGO


def get_article(norma_id: str, numero: int) -> dict | None:
    norma = load_norma(norma_id)
    for article in norma.get("articulos", []):
        if int(article.get("numero", -1)) == int(numero):
            return article
    return None


def search_articles(norma_id: str, query: str, *, limit: int = 40) -> list[dict]:
    query = _normalize(query.strip())
    if not query:
        return []
    norma = load_norma(norma_id)
    results: list[dict] = []

    if query.isdigit():
        article = get_article(norma_id, int(query))
        return [article] if article else []

    for article in norma.get("articulos", []):
        haystack = _normalize(
            f"{article.get('numero', '')} {article.get('seccion', '')} {article.get('texto', '')}"
        )
        if query in haystack:
            results.append(article)
        if len(results) >= limit:
            break
    return results


def list_sections(norma_id: str) -> list[dict]:
    norma = load_norma(norma_id)
    return norma.get("secciones", [])


def format_article_text(article: dict) -> str:
    header = f"Artículo {article.get('numero', '')}. {article.get('norma', '')}"
    section = article.get("seccion")
    if section:
        header += f"\nSección: {section}"
    return f"{header}\n\n{article.get('texto', '').strip()}"


def export_articles_markdown(articles: list[dict]) -> str:
    blocks = [format_article_text(article) for article in articles]
    return "\n\n---\n\n".join(blocks)
