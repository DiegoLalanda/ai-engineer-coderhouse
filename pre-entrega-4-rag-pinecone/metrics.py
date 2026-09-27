"""Precision@k y Recall@k para un único documento fuente esperado."""

from __future__ import annotations


def precision_at_k(
    retrieved_document_ids: list[str],
    expected_document_id: str,
    k: int,
) -> float:
    """Fracción de los k resultados cuyo document_id es el esperado."""
    if k <= 0:
        raise ValueError("k debe ser mayor que cero.")
    useful = sum(
        1
        for document_id in retrieved_document_ids[:k]
        if document_id == expected_document_id
    )
    return useful / k


def recall_at_k(
    retrieved_document_ids: list[str],
    expected_document_id: str,
    k: int,
) -> float:
    """1 si el documento esperado aparece entre los k primeros; si no, 0."""
    if k <= 0:
        raise ValueError("k debe ser mayor que cero.")
    return float(expected_document_id in retrieved_document_ids[:k])
