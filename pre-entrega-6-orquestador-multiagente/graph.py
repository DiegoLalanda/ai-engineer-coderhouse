"""Grafo jerárquico. El supervisor enruta; los especialistas ejecutan."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents import build_analista, build_investigador
from settings import settings
from state import AgentState, AnalysisArtifact, ResearchArtifact, Siguiente

logger = logging.getLogger("orquestador.supervisor")

PEDIDO_DEMO = (
    "Investigá las reseñas de la Notebook 14. En la primera lectura buscá solo la batería. "
    "Si no hay al menos 2 reseñas, ampliá al producto completo y decime si el sentimiento "
    "promedio alcanza para destacarla. El umbral es 0.7."
)

SUPERVISOR_PROMPT = """
Sos el supervisor de un orquestador de reseñas. No busques fichas ni calculés el sentimiento.
Eso lo hacen el Investigador y el Analista. Vos decidís quién interviene ahora.

Te paso un JSON con el pedido, el paso actual, el tope y el resumen de cada parcela.
No vas a ver el historial crudo ni las herramientas.

Rúbrica, en este orden:
- Si pasos es mayor que tope, respondé FINALIZAR.
- Si investigacion es null, respondé Investigador.
- Si hay investigación y analisis es null, respondé Analista.
- Si analisis.suficiente es true, respondé FINALIZAR.
- Si analisis.suficiente es false y investigacion.muestra es mayor que analisis.muestra, respondé Analista.
- Si analisis.suficiente es false y la muestra no creció, respondé Investigador.

Respondé únicamente con una de estas tres palabras, sin explicación:
Investigador
Analista
FINALIZAR
""".strip()

_OPCIONES = frozenset({"Investigador", "Analista", "FINALIZAR"})


def _pedido(state: AgentState) -> str:
    for message in state["messages"]:
        if message.type == "human" and isinstance(message.content, str):
            return message.content
    return ""


def _investigacion(state: AgentState) -> dict[str, Any] | None:
    research = state.get("research")
    if isinstance(research, ResearchArtifact):
        return {
            "muestra": research.muestra,
            "confidence": research.confidence,
            "consulta": research.consulta,
            "producto": research.producto,
        }
    return None


def _analisis(state: AgentState) -> dict[str, Any] | None:
    analysis = state.get("analysis")
    if isinstance(analysis, AnalysisArtifact):
        return {
            "muestra": analysis.muestra,
            "suficiente": analysis.suficiente,
            "score": analysis.score,
            "destacar": analysis.destacar,
            "sentimiento": analysis.sentimiento,
        }
    return None


def resumen_para_supervisor(state: AgentState, pasos: int) -> str:
    """Contrato corto. El supervisor no recibe metadata de herramientas ni el otro prompt."""
    return json.dumps(
        {
            "pedido": _pedido(state),
            "pasos": pasos,
            "tope": settings.max_steps,
            "investigacion": _investigacion(state),
            "analisis": _analisis(state),
        },
        ensure_ascii=False,
    )


def sintesis(state: AgentState) -> tuple[str, bool]:
    research = state.get("research")
    analysis = state.get("analysis")
    if not isinstance(research, ResearchArtifact) or not isinstance(analysis, AnalysisArtifact):
        return (
            "Síntesis: no hay evidencia suficiente para cerrar el pedido. "
            "Corté para no entrar en un bucle de correcciones.",
            False,
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


def _decision(text: str) -> Siguiente:
    token = text.strip().split()[0] if text.strip() else ""
    token = token.strip(".,:;")
    if token in _OPCIONES:
        return cast(Siguiente, token)
    logger.warning("supervisor: decisión inválida %r", text)
    return "FINALIZAR"


def elegir_siguiente(state: AgentState) -> Siguiente:
    """La arista condicional lee next. El Literal es el contrato con el grafo."""
    return state["next"]


def build_graph(
    model: BaseChatModel | Runnable[Any, Any],
) -> CompiledStateGraph[AgentState, Any, AgentState, AgentState]:
    investigador = build_investigador(model)
    analista = build_analista(model)

    async def supervisor_node(state: AgentState) -> dict[str, Any]:
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

    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("Investigador", investigador)
    workflow.add_node("Analista", analista)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("Investigador", "supervisor")
    workflow.add_edge("Analista", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        elegir_siguiente,
        {
            "Investigador": "Investigador",
            "Analista": "Analista",
            "FINALIZAR": END,
        },
    )
    return workflow.compile()
