"""Orquestador del módulo 6. El supervisor enruta; la publicación espera a una persona."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import build_analista, build_investigador
from app.hitl import nodo_aprobacion
from app.observability import tramo
from app.settings import settings
from app.state import AgentState, Siguiente, leer_analisis, leer_investigacion

logger = logging.getLogger("api-agente.supervisor")

PEDIDO_DEMO = (
    "Investigá las reseñas de la Notebook 14. En la primera lectura buscá solo la batería. "
    "Si no hay al menos 2 reseñas, ampliá al producto completo y decime si el sentimiento "
    "promedio alcanza para destacarla. El umbral es 0.7."
)

SUPERVISOR_PROMPT = """
Sos el supervisor de un orquestador de reseñas. No busques fichas, no calculés el sentimiento
y no publiques destacados. Eso lo hacen el Investigador, el Analista y el nodo de Aprobacion.

Te paso un JSON con el pedido, el paso actual, el tope y el resumen de cada parcela.
No vas a ver el historial crudo ni las herramientas.

Rúbrica, en este orden:
- Si pasos es mayor que tope, respondé FINALIZAR.
- Si investigacion es null, respondé Investigador.
- Si hay investigación y analisis es null, respondé Analista.
- Si analisis.suficiente es false y investigacion.muestra es mayor que analisis.muestra, respondé Analista.
- Si analisis.suficiente es false y la muestra no creció, respondé Investigador.
- Si analisis.destacar es true y aprobado es null, respondé Aprobacion.
- En cualquier otro caso, respondé FINALIZAR.

Publicar un destacado es una acción crítica: tiene efecto en la vidriera y no se ejecuta sin Aprobacion.

Respondé únicamente con una de estas cuatro palabras, sin explicación:
Investigador
Analista
Aprobacion
FINALIZAR
""".strip()

_OPCIONES = frozenset({"Investigador", "Analista", "Aprobacion", "FINALIZAR"})


def resumen_para_supervisor(state: AgentState, pasos: int) -> str:
    research = leer_investigacion(state.get("research"))
    analysis = leer_analisis(state.get("analysis"))
    return json.dumps(
        {
            "pedido": _pedido(state),
            "pasos": pasos,
            "tope": settings.max_steps,
            "investigacion": None
            if research is None
            else {
                "muestra": research.muestra,
                "confidence": research.confidence,
                "consulta": research.consulta,
                "producto": research.producto,
            },
            "analisis": None
            if analysis is None
            else {
                "muestra": analysis.muestra,
                "suficiente": analysis.suficiente,
                "score": analysis.score,
                "destacar": analysis.destacar,
                "sentimiento": analysis.sentimiento,
            },
            "aprobado": state.get("aprobado", None),
        },
        ensure_ascii=False,
    )


def sintesis(state: AgentState) -> tuple[str, bool]:
    research = leer_investigacion(state.get("research"))
    analysis = leer_analisis(state.get("analysis"))
    if research is None or analysis is None:
        return (
            "Síntesis: no hay evidencia suficiente para cerrar el pedido. "
            "Corté para no entrar en un bucle de correcciones.",
            False,
        )
    if state.get("publicado"):
        fuentes = ", ".join(research.fuentes)
        return (
            f"Síntesis: se publica el destacado de {analysis.producto}. "
            f"Score {analysis.score:.2f} sobre {analysis.muestra} reseñas ({fuentes}).",
            True,
        )
    if analysis.destacar and state.get("aprobado") is False:
        return (
            f"Síntesis: no se publica el destacado de {analysis.producto}. "
            f"El revisor rechazó la acción. Score {analysis.score:.2f}.",
            True,
        )
    if not analysis.suficiente:
        return (
            "Síntesis: la muestra sigue corta y corté por el tope de pasos. "
            f"Quedaron {analysis.muestra} reseñas de {analysis.producto}.",
            False,
        )
    destaca = "conviene destacarla" if analysis.destacar else "no alcanza para destacarla"
    fuentes = ", ".join(research.fuentes)
    return (
        f"Síntesis: {analysis.producto} tiene {analysis.muestra} reseñas ({fuentes}). "
        f"Sentimiento {analysis.sentimiento} con score {analysis.score:.2f}. "
        f"Umbral {settings.umbral_destacado:.2f}: {destaca}.",
        True,
    )


def elegir_siguiente(state: AgentState) -> Siguiente:
    token = state.get("next") or "FINALIZAR"
    if token not in _OPCIONES:
        return "FINALIZAR"
    return cast(Siguiente, token)


def build_graph(
    model: BaseChatModel | Runnable[Any, Any],
    checkpointer,
) -> CompiledStateGraph:
    investigador = build_investigador(model)
    analista = build_analista(model)

    async def supervisor_node(state: AgentState) -> dict[str, Any]:
        with tramo("supervisor", pasos=int(state.get("steps") or 0) + 1):
            pasos = int(state.get("steps") or 0) + 1
            if pasos > settings.max_steps:
                logger.warning("supervisor: tope de %s pasos", settings.max_steps)
                texto, lista = sintesis(state)
                return {
                    "next": "FINALIZAR",
                    "steps": pasos,
                    "task_completed": lista,
                    "messages": [AIMessage(content=texto, name="Supervisor")],
                }
            response = await model.ainvoke(
                [
                    SystemMessage(content=SUPERVISOR_PROMPT),
                    HumanMessage(content=resumen_para_supervisor(state, pasos)),
                ]
            )
            content = response.content if isinstance(response.content, str) else ""
            choice = _decision(content)
            logger.info("supervisor -> %s (paso %s)", choice, pasos)
            if choice == "FINALIZAR":
                texto, lista = sintesis(state)
                return {
                    "next": "FINALIZAR",
                    "steps": pasos,
                    "task_completed": lista,
                    "messages": [AIMessage(content=texto, name="Supervisor")],
                }
            return {
                "next": choice,
                "steps": pasos,
                "task_completed": False,
                "messages": [AIMessage(content=choice, name="Supervisor")],
            }

    async def correr_investigador(state: AgentState) -> dict[str, Any]:
        with tramo("Investigador"):
            return await investigador(state)

    async def correr_analista(state: AgentState) -> dict[str, Any]:
        with tramo("Analista"):
            return await analista(state)

    def correr_aprobacion(state: AgentState) -> dict[str, Any]:
        with tramo("Aprobacion"):
            return nodo_aprobacion(state)

    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("Investigador", correr_investigador)
    workflow.add_node("Analista", correr_analista)
    workflow.add_node("Aprobacion", correr_aprobacion)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("Investigador", "supervisor")
    workflow.add_edge("Analista", "supervisor")
    workflow.add_edge("Aprobacion", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        elegir_siguiente,
        {
            "Investigador": "Investigador",
            "Analista": "Analista",
            "Aprobacion": "Aprobacion",
            "FINALIZAR": END,
        },
    )
    return workflow.compile(checkpointer=checkpointer)


def _decision(text: str) -> Siguiente:
    token = text.strip().split()[-1] if text.strip() else ""
    token = token.strip(".,:;")
    if token in _OPCIONES:
        return cast(Siguiente, token)
    logger.warning("supervisor: decisión inválida %r", text)
    return "FINALIZAR"


def _pedido(state: AgentState) -> str:
    for message in state.get("messages") or []:
        if getattr(message, "type", "") == "human" and isinstance(message.content, str):
            return message.content
    return ""
