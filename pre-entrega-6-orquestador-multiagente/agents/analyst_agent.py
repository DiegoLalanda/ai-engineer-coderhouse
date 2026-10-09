"""Analista. Puntúa las reseñas que ya reunió el investigador y escribe solo analysis."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from settings import settings
from state import AgentState, AnalysisArtifact

logger = logging.getLogger("orquestador.analista")

PROMPT = """
Sos el analista de sentimiento. No busques reseñas ni abras fichas.

Tenés una sola herramienta: calcular_sentimiento.
Llamala con el producto, el umbral, el mínimo de reseñas y todos los textos del bloque DATOS.
No resumás ni descartes textos. No inventes el score: el número sale de la herramienta.

Cuando la herramienta responda, contestá "Listo."
""".strip()

_POSITIVAS = frozenset(
    {
        "excelente",
        "rápida",
        "rapida",
        "recomiendo",
        "cómodo",
        "comodo",
        "bien",
        "bárbaro",
        "barbaro",
        "comprar",
        "dura",
    }
)
_NEGATIVAS = frozenset({"tarde", "malo", "mala", "rompieron", "defecto"})


class CalcularSentimientoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producto: str = Field(min_length=1, description="Nombre del producto tal como figura en las reseñas.")
    textos: list[str] = Field(min_length=1, description="Textos completos de las reseñas, sin resumir.")
    umbral: float = Field(default=0.7, ge=0, le=1, description="Score mínimo para destacar. Default 0.7.")
    minimo_resenas: int = Field(default=2, ge=1, description="Cantidad mínima de reseñas para dar la muestra por suficiente.")


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", texto.casefold())


def puntuar_texto(texto: str) -> float:
    palabras = _palabras(texto)
    positivas = sum(1 for palabra in palabras if palabra in _POSITIVAS)
    negativas = sum(1 for palabra in palabras if palabra in _NEGATIVAS)
    if positivas + negativas == 0:
        return 0.5
    return positivas / (positivas + negativas)


def puntuar(
    textos: list[str],
    *,
    producto: str,
    umbral: float,
    minimo_resenas: int,
) -> dict[str, Any]:
    scores = [puntuar_texto(texto) for texto in textos]
    score = round(sum(scores) / len(scores), 2)
    muestra = len(textos)
    suficiente = muestra >= minimo_resenas
    if score >= 0.7:
        sentimiento = "positivo"
    elif score <= 0.4:
        sentimiento = "negativo"
    else:
        sentimiento = "neutral"
    return {
        "producto": producto,
        "score": score,
        "muestra": muestra,
        "sentimiento": sentimiento,
        "suficiente": suficiente,
        "destacar": suficiente and score >= umbral,
    }


@tool(args_schema=CalcularSentimientoInput)
async def calcular_sentimiento(
    producto: str,
    textos: list[str],
    umbral: float = 0.7,
    minimo_resenas: int = 2,
) -> str:
    """
    Calcula el sentimiento promedio de una lista de reseñas.

    Usala con todos los textos que entregó el investigador, el umbral del pedido
    y el mínimo de reseñas. No busca fuentes.

    Límites: no acepta la lista vacía. El umbral tiene que estar entre 0 y 1.
    suficiente queda en false si hay menos reseñas que minimo_resenas.
    destacar exige suficiente y score >= umbral.

    Returns:
        JSON con producto, score, muestra, sentimiento, suficiente y destacar.
    """
    try:
        payload = puntuar(
            textos,
            producto=producto,
            umbral=umbral,
            minimo_resenas=minimo_resenas,
        )
    except Exception as exc:
        logger.warning("calcular_sentimiento falló: %s", exc)
        payload = {"error": f"No pude calcular el sentimiento: {exc}"}
    return _dump(payload)


def _json_de(message: BaseMessage) -> dict[str, Any] | None:
    if message.type != "tool" or not isinstance(message.content, str):
        return None
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        logger.warning("Analista: la herramienta no devolvió JSON")
        return None
    return payload if isinstance(payload, dict) else None


def armar_analisis(messages: list[BaseMessage]) -> AnalysisArtifact | None:
    calculos = [
        payload
        for message in messages
        if message.name == "calcular_sentimiento" and (payload := _json_de(message)) is not None
    ]
    if not calculos:
        logger.warning("Analista: cerró sin llamar a calcular_sentimiento")
        return None
    ultimo = calculos[-1]
    if ultimo.get("error"):
        logger.warning("Analista: cálculo rechazado: %s", ultimo["error"])
        return None
    try:
        return AnalysisArtifact.model_validate(ultimo)
    except ValidationError as exc:
        logger.warning("Analista: artefacto inválido: %s", exc)
        return None


def brief_analisis(state: AgentState) -> str:
    """Solo las reseñas ya aceptadas. No incluye la rúbrica del supervisor ni otras herramientas."""
    research = state.get("research")
    if research is None:
        return "DATOS:\nnull"
    datos = {
        "producto": research.producto,
        "umbral": settings.umbral_destacado,
        "minimo_resenas": settings.minimo_resenas,
        "textos": research.findings,
    }
    return "DATOS:\n" + json.dumps(datos, ensure_ascii=False)


def _mensajes_de_herramientas(messages: list[BaseMessage], cierre: AIMessage) -> list[BaseMessage]:
    kept: list[BaseMessage] = []
    for message in messages:
        if message.type == "human":
            continue
        if message.type == "ai" and not getattr(message, "tool_calls", None):
            continue
        kept.append(message)
    kept.append(cierre)
    return kept


def build_analista(model: BaseChatModel | Runnable[Any, Any]):
    agent = create_react_agent(model, [calcular_sentimiento], prompt=PROMPT)

    async def analista_node(state: AgentState) -> dict[str, Any]:
        if state.get("research") is None:
            logger.warning("Analista: no hay investigación para puntuar")
            return {
                "messages": [
                    AIMessage(content="No hay reseñas para analizar.", name="Analista")
                ]
            }
        try:
            result = await agent.ainvoke({"messages": [HumanMessage(content=brief_analisis(state))]})
        except Exception as exc:
            logger.warning("Analista: el ReAct falló: %s", exc)
            return {"messages": [AIMessage(content=f"Análisis interrumpido: {exc}", name="Analista")]}
        child = list(result["messages"])
        artifact = armar_analisis(child)
        if artifact is None:
            return {
                "messages": [AIMessage(content="No pude dejar un análisis válido.", name="Analista")]
            }
        cierre = AIMessage(
            content=(
                f"Análisis: producto={artifact.producto}, score={artifact.score}, "
                f"muestra={artifact.muestra}, sentimiento={artifact.sentimiento}, "
                f"suficiente={str(artifact.suficiente).lower()}, "
                f"destacar={str(artifact.destacar).lower()}."
            ),
            name="Analista",
        )
        return {
            "analysis": artifact,
            "messages": _mensajes_de_herramientas(child, cierre),
        }

    return analista_node
