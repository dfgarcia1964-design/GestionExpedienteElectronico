"""Construye data/colombia_normas/constitucion.json desde texto oficial."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "colombia_normas" / "constitucion.json"
SOURCE_URL = "https://www1.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=4125"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _strip_references(text: str) -> str:
    cut_markers = (
        "Jurisprudencia Vigencia",
        "Leyes y Sentencias",
        "Ver la Constitución Política de 1886",
    )
    for marker in cut_markers:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
    text = re.sub(r"\(Ver [^)]+\)", "", text)
    text = re.sub(r"\(ver [^)]+\)", "", text)
    return _clean(text)


def _fetch_source() -> str:
    local = ROOT / "data" / "colombia_normas" / "constitucion_fuente.txt"
    if local.exists():
        return local.read_text(encoding="utf-8", errors="replace")

    import urllib.request

    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "garciabermeo.net-iley-builder/1.0"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read().decode("latin-1", errors="replace")


def parse_constitution(raw: str) -> dict:
    start = raw.find("CONSTITUCI")
    if start < 0:
        raise ValueError("No se encontró el cuerpo de la Constitución en la fuente.")
    body = raw[start:]
    parts = re.split(r"ART.{1,8}?CULO\s+(\d+)\.?\s*", body, flags=re.IGNORECASE)
    preamble = _clean(parts[0].split("DE LOS PRINCIPIOS", 1)[0])

    sections: list[dict] = []
    current_section = "Disposiciones generales"
    articles: list[dict] = []

    for idx in range(1, len(parts), 2):
        number = int(parts[idx])
        chunk = parts[idx + 1]
        chunk = _strip_references(chunk)
        if not chunk:
            continue

        pre_lines = chunk.split("\n")
        title_hint = ""
        body_lines: list[str] = []
        for line in pre_lines:
            stripped = line.strip()
            if not stripped:
                continue
            norm_line = _norm(stripped)
            if (
                len(stripped) < 120
                and stripped == stripped.upper()
                and any(word in norm_line for word in ("titulo", "capitulo", "de los", "de las", "disposiciones"))
            ):
                current_section = stripped.title()
                continue
            if not title_hint and len(stripped) <= 90 and stripped.endswith(":"):
                title_hint = stripped
                continue
            body_lines.append(stripped)
        text = _clean(" ".join(body_lines))
        if not text:
            continue

        article = {
            "numero": number,
            "seccion": current_section,
            "titulo": title_hint,
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
        "fuente": SOURCE_URL,
        "preambulo": preamble[:2000],
        "secciones": sections,
        "articulos": articles,
    }


def main() -> None:
    raw = _fetch_source()
    corpus = parse_constitution(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Artículos: {len(corpus['articulos'])} -> {OUT}")


if __name__ == "__main__":
    main()
