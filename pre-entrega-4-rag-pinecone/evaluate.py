"""Evalúa el recuperador híbrido contra el golden set."""

from __future__ import annotations

import json
import sys

from config import settings
from metrics import precision_at_k, recall_at_k
from rag_system import RAGSystem


def load_golden_set() -> list[dict[str, str]]:
    cases = json.loads(settings.golden_set_path.read_text(encoding="utf-8"))
    if len(cases) < 5:
        raise ValueError("El golden set debe tener al menos 5 preguntas.")
    for case in cases:
        if not case.get("pregunta") or not case.get("documento_id_esperado"):
            raise ValueError("Cada caso necesita pregunta y documento_id_esperado.")
    return cases


def evaluate(system: RAGSystem | None = None) -> dict[str, float]:
    cases = load_golden_set()
    system = system or RAGSystem()
    precisions: list[float] = []
    recalls: list[float] = []

    print(f"Evaluación híbrida top-{settings.top_k} | namespace {settings.namespace}")
    print("-" * 72)
    for number, case in enumerate(cases, start=1):
        retrieved = system.retrieve(case["pregunta"])
        retrieved_ids = [
            str(document.metadata.get("document_id", "")) for document in retrieved
        ]
        precision = precision_at_k(
            retrieved_ids, case["documento_id_esperado"], settings.top_k
        )
        recall = recall_at_k(
            retrieved_ids, case["documento_id_esperado"], settings.top_k
        )
        precisions.append(precision)
        recalls.append(recall)
        found = "sí" if recall == 1 else "no"
        print(f"{number}. {case['pregunta']}")
        print(f"   Esperado: {case['documento_id_esperado']} | encontrado: {found}")
        print(f"   Recuperados: {', '.join(retrieved_ids) or '(ninguno)'}")
        print(f"   Precision@{settings.top_k}={precision:.2f}  Recall@{settings.top_k}={recall:.2f}")

    mean_precision = sum(precisions) / len(precisions)
    mean_recall = sum(recalls) / len(recalls)
    print("-" * 72)
    print(
        f"Promedio Precision@{settings.top_k}: {mean_precision:.2f} | "
        f"Promedio Recall@{settings.top_k}: {mean_recall:.2f}"
    )
    print(
        "Precision@5 es la fracción de los 5 chunks cuyo document_id coincide "
        "con la fuente esperada. Recall@5 es 1 cuando esa fuente aparece al menos una vez."
    )
    return {
        "precision_at_5": mean_precision,
        "recall_at_5": mean_recall,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        evaluate()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error de evaluación: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
