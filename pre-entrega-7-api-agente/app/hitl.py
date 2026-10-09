"""Pausa antes de publicar. La herramienta con efecto corre recién después del resume."""

from __future__ import annotations

import json
import logging

from langgraph.types import interrupt

from app.settings import settings
from app.state import AgentState, leer_analisis

logger = logging.getLogger("api-agente.hitl")


def publicar_destacado(producto: str, score: float) -> None:
    """Efecto secundario: deja asentado el destacado. No se llama sin aprobación."""
    carpeta = settings.evidencia_dir
    carpeta.mkdir(parents=True, exist_ok=True)
    with (carpeta / "publicaciones.jsonl").open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps({"producto": producto, "score": score}, ensure_ascii=False) + "\n")


def nodo_aprobacion(state: AgentState) -> dict:
    analysis = leer_analisis(state.get("analysis"))
    if analysis is None or not analysis.destacar:
        return {"aprobado": False, "publicado": False}
    decision = interrupt(
        {
            "pregunta": f"¿Publicar {analysis.producto} como destacado?",
            "producto": analysis.producto,
            "score": analysis.score,
            "muestra": analysis.muestra,
            "accion": "publicar_destacado",
        }
    )
    if str(decision).strip().lower() != "si":
        logger.info("El revisor rechazó publicar %s.", analysis.producto)
        return {"aprobado": False, "publicado": False}
    publicar_destacado(analysis.producto, analysis.score)
    return {"aprobado": True, "publicado": True}
