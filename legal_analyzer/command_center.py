from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .case_extractor import classify_document
from .models import PageTrace
from .petition_comparator import compare_requests_with_answers, extract_requests
from .text_utils import normalize, split_fragments


NEGATIONS = (
    "no se entrego",
    "no fue entregado",
    "no se realizo",
    "no se autorizo",
    "no se respondio",
    "no se cumplio",
    "no existe",
    "no obra",
    "no consta",
    "pendiente",
    "incumplimiento",
)

AFFIRMATIONS = (
    "se entrego",
    "fue entregado",
    "se realizo",
    "se autorizo",
    "se respondio",
    "se cumplio",
    "se dio cumplimiento",
    "obra constancia",
    "se adjunta",
    "se aporta",
)

IMPORTANT_TERMS = (
    "entrega",
    "autorizacion",
    "audifono",
    "medicamento",
    "respuesta",
    "tratamiento",
    "valoracion",
    "cita",
    "pago",
    "reintegro",
    "expediente",
    "concepto medico",
    "notificacion",
)


@dataclass
class RiskResult:
    score: int
    level: str
    reasons: list[str]
    next_actions: list[str]


def flatten_pages(documents: dict[str, list[PageTrace]]) -> list[PageTrace]:
    return [page for pages in documents.values() for page in pages]


def document_inventory(documents: dict[str, list[PageTrace]]) -> Counter:
    return Counter(
        classify_document(pages)[0]
        for pages in documents.values()
    )


def detect_contradictions(
    documents: dict[str, list[PageTrace]],
) -> list[dict]:
    """
    Detecta contradicciones potenciales y conserva el texto completo
    de ambas versiones, sin recortes.
    """
    statements: list[dict] = []

    for name, pages in documents.items():
        for page in pages:
            for fragment in split_fragments(page.text, min_length=20):
                normalized = normalize(fragment)

                polarity = ""
                if any(term in normalized for term in NEGATIONS):
                    polarity = "negativa"
                elif any(term in normalized for term in AFFIRMATIONS):
                    polarity = "afirmativa"

                if not polarity:
                    continue

                topics = [
                    term
                    for term in IMPORTANT_TERMS
                    if term in normalized
                ]

                if not topics:
                    continue

                statements.append(
                    {
                        "document": name,
                        "page": page.page,
                        "fragment": fragment.strip(),
                        "polarity": polarity,
                        "topics": topics,
                        "method": page.extraction_method,
                        "ocr_confidence": page.ocr_confidence,
                    }
                )

    contradictions: list[dict] = []
    seen: set[tuple] = set()

    for index, left in enumerate(statements):
        for right in statements[index + 1:]:
            if (
                left["document"] == right["document"]
                and left["page"] == right["page"]
            ):
                continue

            shared = sorted(
                set(left["topics"]).intersection(right["topics"])
            )

            if not shared:
                continue

            if left["polarity"] == right["polarity"]:
                continue

            key = (
                left["document"],
                left["page"],
                left["fragment"],
                right["document"],
                right["page"],
                right["fragment"],
            )

            reverse_key = (
                right["document"],
                right["page"],
                right["fragment"],
                left["document"],
                left["page"],
                left["fragment"],
            )

            if key in seen or reverse_key in seen:
                continue

            seen.add(key)

            contradictions.append(
                {
                    "Tema": ", ".join(shared),
                    "Versión 1 completa": left["fragment"],
                    "Fuente 1": f"{left['document']}, página {left['page']}",
                    "Método 1": left["method"],
                    "Confianza OCR 1": left["ocr_confidence"],
                    "Versión 2 completa": right["fragment"],
                    "Fuente 2": f"{right['document']}, página {right['page']}",
                    "Método 2": right["method"],
                    "Confianza OCR 2": right["ocr_confidence"],
                    "Tipo de oposición": (
                        f"{left['polarity']} ↔ {right['polarity']}"
                    ),
                    "Evaluación": (
                        "Contradicción potencial; debe compararse el contexto "
                        "completo de ambas fuentes."
                    ),
                    "Conclusión revisada": "",
                    "Observaciones": "",
                }
            )

    return contradictions


def assess_risk(
    documents: dict[str, list[PageTrace]],
    quality_rows: list[dict],
) -> RiskResult:
    inventory = document_inventory(documents)
    reasons: list[str] = []
    actions: list[str] = []
    score = 0

    if inventory["Acción de tutela"] > 0 and inventory["Fallo de tutela"] == 0:
        score += 18
        reasons.append("Se identificó tutela, pero no fallo.")
        actions.append(
            "Verificar el estado del proceso y solicitar copia del fallo o del expediente."
        )

    if inventory["Fallo de tutela"] > 0 and inventory["Respuesta de cumplimiento"] == 0:
        score += 18
        reasons.append("Existe fallo sin respuesta de cumplimiento identificada.")
        actions.append(
            "Revisar las órdenes del fallo y solicitar prueba material de cumplimiento."
        )

    if inventory["Incidente de desacato"] > 0 and inventory["Fallo de tutela"] == 0:
        score += 15
        reasons.append("Hay desacato sin fallo fuente dentro de los archivos.")
        actions.append(
            "Incorporar el fallo completo antes de valorar el desacato."
        )

    low_quality = sum(
        row.get("Calidad") == "Baja"
        for row in quality_rows
    )

    if low_quality:
        penalty = min(20, low_quality * 3)
        score += penalty
        reasons.append(
            f"{low_quality} página(s) presentan calidad de lectura baja."
        )
        actions.append(
            "Revisar las páginas de baja calidad o reemplazarlas por copias más legibles."
        )

    petition_docs = [
        name
        for name, pages in documents.items()
        if classify_document(pages)[0] == "Derecho de petición"
    ]

    answer_pages = [
        page
        for name, pages in documents.items()
        if name not in petition_docs
        for page in pages
    ]

    unanswered = 0

    for petition_name in petition_docs:
        requests = extract_requests(documents[petition_name])
        comparison = compare_requests_with_answers(
            requests,
            answer_pages,
        )

        unanswered += sum(
            row["Evaluación automática"]
            == "Sin respuesta localizada"
            for row in comparison
        )

    if unanswered:
        score += min(25, unanswered * 5)
        reasons.append(
            f"Se detectaron {unanswered} solicitud(es) sin respuesta localizada."
        )
        actions.append(
            "Contrastar cada pregunta con la respuesta y preparar requerimiento o tutela, según el término aplicable."
        )

    contradictions = detect_contradictions(documents)

    if contradictions:
        score += min(20, len(contradictions) * 4)
        reasons.append(
            f"Se detectaron {len(contradictions)} contradicción(es) potencial(es)."
        )
        actions.append(
            "Revisar el texto completo de cada versión y verificar cuál está respaldada."
        )

    score = min(100, score)

    if score >= 70:
        level = "Crítico"
    elif score >= 45:
        level = "Alto"
    elif score >= 25:
        level = "Medio"
    else:
        level = "Bajo"

    if not reasons:
        reasons.append(
            "No se detectaron alertas estructurales graves con las reglas actuales."
        )

    if not actions:
        actions.append(
            "Completar la revisión humana y validar fechas, fuentes y anexos."
        )

    return RiskResult(
        score=score,
        level=level,
        reasons=reasons,
        next_actions=list(dict.fromkeys(actions)),
    )


def executive_summary(
    documents: dict[str, list[PageTrace]],
    risk: RiskResult,
    contradictions: list[dict],
) -> str:
    inventory = document_inventory(documents)
    inventory_text = ", ".join(
        f"{kind}: {count}"
        for kind, count in inventory.most_common()
    )

    return (
        f"Se analizaron {len(documents)} documentos. "
        f"Inventario procesal: {inventory_text or 'sin clasificación concluyente'}. "
        f"El nivel de riesgo preliminar es {risk.level} "
        f"({risk.score}/100). "
        f"Se identificaron {len(contradictions)} contradicciones potenciales. "
        "Este resultado es preliminar y debe contrastarse con el expediente original."
    )
