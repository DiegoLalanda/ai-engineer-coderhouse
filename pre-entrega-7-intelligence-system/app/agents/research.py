"""Investigador. Busca políticas y reseñas. No puntúa y no publica."""

from __future__ import annotations

import json
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, ValidationError

from app.knowledge import indice
from app.reviews import buscar_fichas, leer_ficha
from app.settings import settings
from app.state import AgentState, Fragmento, ResearchArtifact

logger = logging.getLogger("intelligence.investigador")

PROMPT = """
Sos el investigador de la tienda. No puntúes sentimiento y no publiques nada.

Tenés dos herramientas: buscar_conocimiento y buscar_resenas.
Llamá a las dos, una vez cada una, con la consulta del pedido.
Si una ficha te interesa, podés abrirla con obtener_resena.
No inventes fuentes ni textos.

Cuando las herramientas respondan, contestá "Listo."
""".strip()


class ConsultaTool(BaseModel):
    consulta: str = Field(min_length=1)


class FichaTool(BaseModel):
    resena_id: str = Field(min_length=1)


@tool(args_schema=ConsultaTool)
async def buscar_conocimiento(consulta: str) -> str:
    """Recupera fragmentos de las políticas internas que responden la consulta."""

    def _buscar() -> list[dict[str, str]]:
        return indice.buscar(consulta)

    fragmentos = await _a_hilo(_buscar)
    return json.dumps({"fragmentos": fragmentos}, ensure_ascii=False)


@tool(args_schema=ConsultaTool)
async def buscar_resenas(consulta: str) -> str:
    """Busca fichas de reseña cuyo producto o texto coinciden con la consulta."""
    fichas = await buscar_fichas(consulta)
    hallazgos = [
        {
            "id": ficha["id"],
            "producto": ficha.get("producto", ""),
            "texto": ficha.get("texto", ""),
        }
        for ficha in fichas
        if ficha.get("id") and ficha.get("texto")
    ]
    return json.dumps({"consulta": consulta, "hallazgos": hallazgos}, ensure_ascii=False)


@tool(args_schema=FichaTool)
async def obtener_resena(resena_id: str) -> str:
    """Abre una ficha de reseña por su id. No inventa el texto."""
    ficha = await leer_ficha(resena_id)
    if ficha is None:
        return json.dumps({"error": "no existe"})
    return json.dumps(
        {"id": ficha["id"], "producto": ficha.get("producto", ""), "texto": ficha.get("texto", "")},
        ensure_ascii=False,
    )


async def _a_hilo(funcion):
    import asyncio

    return await asyncio.to_thread(funcion)


def armar_investigacion(messages: list, consulta: str) -> ResearchArtifact | None:
    fragmentos: list[Fragmento] = []
    hallazgos: list[dict] = []
    producto = ""
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            data = json.loads(str(message.content))
        except json.JSONDecodeError:
            continue
        for item in data.get("fragmentos") or []:
            try:
                fragmentos.append(Fragmento.model_validate(item))
            except ValidationError:
                logger.warning("Fragmento inválido descartado.")
        for item in data.get("hallazgos") or []:
            if item.get("texto"):
                hallazgos.append(item)
                producto = producto or str(item.get("producto") or "")
        if data.get("texto") and data.get("id"):
            if not any(item.get("id") == data["id"] for item in hallazgos):
                hallazgos.append(data)
                producto = producto or str(data.get("producto") or "")
    if not fragmentos and not hallazgos:
        return None
    muestra = len(hallazgos)
    if muestra >= settings.minimo_resenas:
        confidence = 0.9
    elif muestra == 1:
        confidence = 0.45
    elif fragmentos:
        confidence = 0.3
    else:
        confidence = 0.0
    return ResearchArtifact(
        consulta=consulta,
        producto=producto,
        findings=[str(item["texto"]) for item in hallazgos],
        fuentes=[str(item["id"]) for item in hallazgos if item.get("id")],
        fragmentos=fragmentos,
        muestra=muestra,
        confidence=confidence,
    )


def brief_investigacion(state: AgentState) -> str:
    pedido = _pedido(state)
    return f"pedido: {pedido}"


def build_investigador(model: BaseChatModel):
    react = create_react_agent(
        model,
        tools=[buscar_conocimiento, buscar_resenas, obtener_resena],
        prompt=PROMPT,
        name="investigador",
    )

    async def investigador(state: AgentState) -> dict:
        pedido = _pedido(state)
        try:
            resultado = await react.ainvoke(
                {"messages": [("user", brief_investigacion(state))]},
                config={"recursion_limit": settings.recursion_limit},
            )
        except Exception:
            logger.warning("El investigador no pudo completar la búsqueda.", exc_info=True)
            return {}
        artefacto = armar_investigacion(resultado.get("messages", []), pedido)
        if artefacto is None:
            logger.warning("La búsqueda no devolvió políticas ni reseñas.")
            return {}
        return {"research": artefacto.model_dump()}

    return investigador


def _pedido(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", "") == "human" or message.__class__.__name__ == "HumanMessage":
            return str(message.content)
        if isinstance(message, AIMessage):
            continue
    return ""
