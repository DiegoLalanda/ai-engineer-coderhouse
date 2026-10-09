"""Pausa de aprobación. El nodo no publica: deja la decisión en el checkpointer hasta el resume."""

from __future__ import annotations

import logging

from langgraph.types import interrupt

from app.state import AgentState, AnalysisArtifact

logger = logging.getLogger("intelligence.hitl")


def nodo_aprobacion(state: AgentState) -> dict:
    crudo = state.get("analysis")
    if not crudo:
        return {"aprobado": False, "publicado": False}
    analysis = AnalysisArtifact.model_validate(crudo)
    if not analysis.destacar:
        return {"aprobado": False, "publicado": False}
    decision = interrupt(
        {
            "pregunta": f"¿Publicar {analysis.producto} como destacado?",
            "producto": analysis.producto,
            "score": analysis.score,
            "muestra": analysis.muestra,
        }
    )
    aprobado = str(decision).strip().lower() == "si"
    if not aprobado:
        logger.info("El revisor rechazó el destacado de %s.", analysis.producto)
    return {"aprobado": aprobado, "publicado": aprobado}
