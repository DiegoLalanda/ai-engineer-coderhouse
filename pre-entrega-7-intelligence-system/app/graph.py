"""Grafo jerárquico. El supervisor enruta; los especialistas ejecutan; la publicación espera a una persona."""

from __future__ import annotations

import json
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import build_analista, build_investigador
from app.hitl import nodo_aprobacion
from app.observability import tramo
from app.settings import settings
from app.state import AgentState, AnalysisArtifact, ResearchArtifact

logger = logging.getLogger("intelligence.supervisor")

SUPERVISOR_PROMPT = """
Sos el supervisor de un sistema de inteligencia comercial. No busques fichas, no calculés el sentimiento
y no publiques destacados. Eso lo hacen el Investigador, el Analista y el nodo de Aprobacion.

Te paso un JSON con el pedido y el resumen de cada parcela. No vas a ver el historial crudo.

Rúbrica, en este orden:
- Si investigacion es null, respondé Investigador.
- Si investigacion.muestra es mayor que 0 y analisis es null, respondé Analista.
- Si analisis.destacar es true y aprobado es null, respondé Aprobacion.
- En cualquier otro caso, respondé FINALIZAR.

Respondé únicamente con una de estas cuatro palabras, sin explicación:
Investigador
Analista
Aprobacion
FINALIZAR
""".strip()

_OPCIONES = frozenset({"Investigador", "Analista", "Aprobacion", "FINALIZAR"})


def resumen_para_supervisor(state: AgentState) -> str:
    research = _research(state)
    analysis = _analysis(state)
    return json.dumps(
        {
            "pedido": _pedido(state),
            "investigacion": None
            if research is None
            else {
                "muestra": research.muestra,
                "confidence": research.confidence,
                "producto": research.producto,
                "fuentes": research.fuentes,
                "politicas": [item.fuente for item in research.fragmentos],
            },
            "analisis": None
            if analysis is None
            else {
                "muestra": analysis.muestra,
                "score": analysis.score,
                "destacar": analysis.destacar,
                "suficiente": analysis.suficiente,
                "sentimiento": analysis.sentimiento,
            },
            "aprobado": state.get("aprobado", None),
        },
        ensure_ascii=False,
    )


def sintesis(state: AgentState, forzado: bool = False) -> str:
    research = _research(state)
    analysis = _analysis(state)
    if forzado or research is None:
        return "Síntesis: corté el pedido antes de juntar evidencia suficiente."
    politicas = ", ".join(item.fuente for item in research.fragmentos) or "sin política recuperada"
    if analysis is None:
        return (
            f"Síntesis: no hay reseñas para puntuar. "
            f"Políticas consultadas: {politicas}. "
            f"Fragmentos: {_citas(research)}."
        )
    if state.get("publicado"):
        return (
            f"Síntesis: se publica el destacado de {analysis.producto}. "
            f"Score {analysis.score:.2f} sobre {analysis.muestra} reseñas ({', '.join(research.fuentes)}). "
            f"Política: {politicas}."
        )
    if analysis.destacar and state.get("aprobado") is False:
        return (
            f"Síntesis: no se publica el destacado de {analysis.producto}. "
            f"El revisor rechazó la acción. Score {analysis.score:.2f}."
        )
    return (
        f"Síntesis: {analysis.producto} queda con sentimiento {analysis.sentimiento} "
        f"y score {analysis.score:.2f} sobre {analysis.muestra} reseñas. "
        f"No se destaca. Política: {politicas}."
    )


def build_graph(model: BaseChatModel, checkpointer) -> CompiledStateGraph:
    investigador = build_investigador(model)
    analista = build_analista(model)

    async def supervisor(state: AgentState) -> dict:
        with tramo("supervisor", pasos=int(state.get("steps") or 0) + 1):
            pasos = int(state.get("steps") or 0) + 1
            if pasos > settings.max_steps:
                logger.warning("Tope de %s pasos. Cierro el pedido.", settings.max_steps)
                return {
                    "next": "FINALIZAR",
                    "steps": pasos,
                    "task_completed": False,
                    "messages": [AIMessage(content=sintesis(state, forzado=True))],
                }
            respuesta = await model.ainvoke(
                [
                    SystemMessage(content=SUPERVISOR_PROMPT),
                    HumanMessage(content=resumen_para_supervisor(state)),
                ]
            )
            token = _token(str(respuesta.content))
            if token not in _OPCIONES:
                logger.warning("El supervisor respondió %r. Cierro el pedido.", respuesta.content)
                token = "FINALIZAR"
            mensaje = sintesis(state) if token == "FINALIZAR" else f"Siguiente: {token}."
            return {
                "next": token,
                "steps": pasos,
                "task_completed": token == "FINALIZAR",
                "messages": [AIMessage(content=mensaje)],
            }

    async def correr_investigador(state: AgentState) -> dict:
        with tramo("investigador"):
            return await investigador(state)

    async def correr_analista(state: AgentState) -> dict:
        with tramo("analista"):
            return await analista(state)

    def correr_aprobacion(state: AgentState) -> dict:
        with tramo("aprobacion"):
            return nodo_aprobacion(state)

    grafo = StateGraph(AgentState)
    grafo.add_node("supervisor", supervisor)
    grafo.add_node("Investigador", correr_investigador)
    grafo.add_node("Analista", correr_analista)
    grafo.add_node("Aprobacion", correr_aprobacion)
    grafo.add_edge(START, "supervisor")
    grafo.add_edge("Investigador", "supervisor")
    grafo.add_edge("Analista", "supervisor")
    grafo.add_edge("Aprobacion", "supervisor")
    grafo.add_conditional_edges(
        "supervisor",
        elegir_siguiente,
        {
            "Investigador": "Investigador",
            "Analista": "Analista",
            "Aprobacion": "Aprobacion",
            "FINALIZAR": END,
        },
    )
    return grafo.compile(checkpointer=checkpointer)


def elegir_siguiente(state: AgentState) -> str:
    return str(state.get("next") or "FINALIZAR")


def _token(texto: str) -> str:
    limpio = texto.strip().split()
    return limpio[-1] if limpio else ""


def _pedido(state: AgentState) -> str:
    for message in state.get("messages") or []:
        if getattr(message, "type", "") == "human":
            return str(message.content)
    return ""


def _research(state: AgentState) -> ResearchArtifact | None:
    crudo = state.get("research")
    if not crudo:
        return None
    return ResearchArtifact.model_validate(crudo)


def _analysis(state: AgentState) -> AnalysisArtifact | None:
    crudo = state.get("analysis")
    if not crudo:
        return None
    return AnalysisArtifact.model_validate(crudo)


def _citas(research: ResearchArtifact) -> str:
    if not research.fragmentos:
        return "ninguno"
    return research.fragmentos[0].texto[:180]
