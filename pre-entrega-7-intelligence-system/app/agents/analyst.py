"""Analista. Puntúa solo las reseñas que ya reunió el investigador."""

from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, ValidationError

from app.settings import settings
from app.state import AgentState, AnalysisArtifact, ResearchArtifact

logger = logging.getLogger("intelligence.analista")

PROMPT = """
Sos el analista de sentimiento. No busques reseñas ni abras políticas.

Tenés una sola herramienta: calcular_sentimiento.
Llamala con el producto, el umbral, el mínimo de reseñas y todos los textos del bloque DATOS.
No inventes el score: el número sale de la herramienta.

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
_TOKEN = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)


class CalcularSentimientoInput(BaseModel):
    producto: str = Field(min_length=1)
    textos: list[str] = Field(min_length=1)
    umbral: float = Field(ge=0.0, le=1.0)
    minimo_resenas: int = Field(ge=1)


@tool(args_schema=CalcularSentimientoInput)
def calcular_sentimiento(producto: str, textos: list[str], umbral: float, minimo_resenas: int) -> str:
    """Calcula el sentimiento promedio y si la muestra alcanza para una decisión."""
    puntajes = [puntuar_texto(texto) for texto in textos]
    score = sum(puntajes) / len(puntajes)
    muestra = len(textos)
    suficiente = muestra >= minimo_resenas
    if score >= umbral:
        sentimiento = "positivo"
    elif score <= 1 - umbral:
        sentimiento = "negativo"
    else:
        sentimiento = "neutral"
    artefacto = AnalysisArtifact(
        producto=producto,
        score=round(score, 2),
        muestra=muestra,
        sentimiento=sentimiento,
        destacar=suficiente and score >= umbral,
        suficiente=suficiente,
    )
    return artefacto.model_dump_json()


def puntuar_texto(texto: str) -> float:
    tokens = [token.lower() for token in _TOKEN.findall(texto)]
    positivas = sum(1 for token in tokens if token in _POSITIVAS)
    negativas = sum(1 for token in tokens if token in _NEGATIVAS)
    total = positivas + negativas
    if total == 0:
        return 0.5
    return positivas / total


def armar_analisis(messages: list) -> AnalysisArtifact | None:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        if getattr(message, "name", "") != "calcular_sentimiento":
            continue
        try:
            return AnalysisArtifact.model_validate_json(str(message.content))
        except ValidationError:
            logger.warning("El analista devolvió un JSON que no cumple el contrato.")
    return None


def brief_analisis(research: ResearchArtifact) -> str:
    datos = {
        "producto": research.producto or "producto",
        "umbral": settings.umbral_sentimiento,
        "minimo_resenas": settings.minimo_resenas,
        "textos": research.findings,
    }
    return "DATOS:\n" + json.dumps(datos, ensure_ascii=False)


def build_analista(model: BaseChatModel):
    react = create_react_agent(
        model,
        tools=[calcular_sentimiento],
        prompt=PROMPT,
        name="analista",
    )

    async def analista(state: AgentState) -> dict:
        crudo = state.get("research")
        if not crudo:
            logger.warning("El analista no recibió investigación.")
            return {}
        research = ResearchArtifact.model_validate(crudo)
        if not research.findings:
            return {}
        try:
            resultado = await react.ainvoke(
                {"messages": [("user", brief_analisis(research))]},
                config={"recursion_limit": settings.recursion_limit},
            )
        except Exception:
            logger.warning("El analista no pudo puntuar.", exc_info=True)
            return {}
        artefacto = armar_analisis(resultado.get("messages", []))
        if artefacto is None:
            return {}
        return {"analysis": artefacto.model_dump()}

    return analista
