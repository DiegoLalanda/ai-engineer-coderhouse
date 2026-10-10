"""Investigador. Lee el corpus de reseñas y escribe solo research."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.knowledge import indice
from app.settings import settings
from app.state import AgentState, Fragmento, ResearchArtifact, leer_investigacion

logger = logging.getLogger("orquestador.investigador")

PROMPT = """
Sos el investigador de reseñas. No calculás sentimiento ni decidís si el producto se destaca.

Tenés tres herramientas y nada más:
- buscar_conocimiento recupera la política interna que aplica al pedido. Llamala una vez, antes de las reseñas.
- buscar_resenas lee todas las fichas en paralelo y devuelve las que coinciden con la consulta.
- obtener_resena abre el texto completo de un id que ya devolvió la búsqueda.

Primera lectura (muestra_actual: 0): después de la política, llamá a buscar_resenas con el aspecto puntual del pedido,
por ejemplo la batería. No abras fichas todavía.
Si muestra_actual es mayor que 0 y no llega al mínimo: buscá el nombre del producto
y después llamá a obtener_resena con un id de esa búsqueda.

No inventes reseñas ni ids. Cuando las herramientas hayan respondido, contestá "Listo."
""".strip()


class BuscarResenasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consulta: str = Field(
        min_length=1,
        description=(
            "Texto a buscar en producto, aspectos y reseña. "
            "Ejemplos: 'batería' o 'Notebook 14'. No lo dejes vacío."
        ),
    )


class ObtenerResenaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resena_id: str = Field(
        min_length=1,
        description="Id devuelto por buscar_resenas. Formato rev-nb-1. No lo inventes.",
    )


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text.casefold())


def _coincide(doc: dict[str, Any], consulta: str) -> bool:
    claves = [token for token in _tokens(consulta) if len(token) >= 4]
    if not claves:
        return False
    aspectos = " ".join(doc.get("aspectos") or [])
    blob = f"{doc.get('producto', '')} {doc.get('texto', '')} {aspectos}".casefold()
    return all(clave in blob for clave in claves)


async def _leer(path: Path) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    return await asyncio.to_thread(_read)


def _fichas() -> list[Path]:
    return sorted(settings.corpus_dir.glob("*.json"))


@tool(args_schema=BuscarResenasInput)
async def buscar_conocimiento(consulta: str) -> str:
    """Recupera fragmentos de las políticas internas que responden la consulta. No inventa fuentes."""

    def _buscar() -> list[dict[str, str]]:
        return indice.buscar(consulta)

    fragmentos = await asyncio.to_thread(_buscar)
    return _dump({"fragmentos": fragmentos})


@tool(args_schema=BuscarResenasInput)
async def buscar_resenas(consulta: str) -> str:
    """
    Busca reseñas en las fichas locales. Las lee todas a la vez.

    Usala para una primera lectura por aspecto o para ampliar al producto entero.
    No calcula sentimiento. Si no hay coincidencias, el JSON trae error y resultados vacíos.

    Límites: solo lectura. La consulta no puede ir vacía.

    Returns:
        JSON con consulta, resultados (id, producto, texto), muestra y confidence.
        confidence es 0.45 con una sola reseña y 0.9 con dos o más.
    """
    try:
        paths = _fichas()
        if not paths:
            raise FileNotFoundError(f"No hay fichas en {settings.corpus_dir}")
        docs = await asyncio.gather(*[_leer(path) for path in paths])
        hits = [doc for doc in docs if _coincide(doc, consulta)]
        muestra = len(hits)
        payload: dict[str, Any] = {
            "consulta": consulta,
            "resultados": [
                {"id": doc["id"], "producto": doc["producto"], "texto": doc["texto"]}
                for doc in hits
            ],
            "muestra": muestra,
            "confidence": 0.9 if muestra >= settings.minimo_resenas else 0.45 if muestra else 0.0,
        }
        if muestra == 0:
            payload["error"] = f"Ninguna ficha coincide con {consulta!r}."
    except Exception as exc:
        logger.warning("buscar_resenas falló: %s", exc)
        payload = {
            "consulta": consulta,
            "resultados": [],
            "muestra": 0,
            "confidence": 0.0,
            "error": f"Error al leer reseñas: {exc}",
        }
    return _dump(payload)


@tool(args_schema=ObtenerResenaInput)
async def obtener_resena(resena_id: str) -> str:
    """
    Abre una ficha por id.

    Usala después de buscar_resenas, con un id que esa búsqueda haya devuelto.
    No lista el catálogo ni calcula sentimiento.

    Límites: solo lectura. Si el id no existe, el JSON trae error.

    Returns:
        JSON con id, producto y texto de esa reseña.
    """
    try:
        path = settings.corpus_dir / f"{resena_id}.json"
        if not path.is_file():
            raise FileNotFoundError(resena_id)
        doc = await _leer(path)
        payload = {"id": doc["id"], "producto": doc["producto"], "texto": doc["texto"]}
    except Exception as exc:
        logger.warning("obtener_resena falló para %s: %s", resena_id, exc)
        payload = {"id": resena_id, "error": f"No pude abrir la ficha: {exc}"}
    return _dump(payload)


def _json_de(message: BaseMessage) -> dict[str, Any] | None:
    if message.type != "tool" or not isinstance(message.content, str):
        return None
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        logger.warning("Investigador: herramienta devolvió texto que no es JSON")
        return None
    return payload if isinstance(payload, dict) else None


def armar_investigacion(messages: list[BaseMessage]) -> ResearchArtifact | None:
    """Arma la parcela desde las herramientas. El modelo no inventa el artefacto."""
    busquedas = [
        payload
        for message in messages
        if message.name == "buscar_resenas" and (payload := _json_de(message)) is not None
    ]
    if not busquedas:
        logger.warning("Investigador: cerró sin llamar a buscar_resenas")
        return None
    ultima = busquedas[-1]
    if ultima.get("error") and not ultima.get("resultados"):
        logger.warning("Investigador: búsqueda sin resultados: %s", ultima.get("error"))
        return None
    textos = {
        item["id"]: item["texto"]
        for item in ultima.get("resultados") or []
        if item.get("id") and item.get("texto")
    }
    producto = ""
    for item in ultima.get("resultados") or []:
        if item.get("producto"):
            producto = str(item["producto"])
            break
    for message in messages:
        if message.name != "obtener_resena":
            continue
        payload = _json_de(message)
        if not payload or payload.get("error") or "texto" not in payload:
            continue
        textos[str(payload["id"])] = str(payload["texto"])
        producto = producto or str(payload.get("producto") or "")
    muestra = len(textos)
    fragmentos: list[Fragmento] = []
    for message in messages:
        if message.name != "buscar_conocimiento":
            continue
        payload = _json_de(message)
        for item in (payload or {}).get("fragmentos") or []:
            try:
                fragmentos.append(Fragmento.model_validate(item))
            except ValidationError:
                logger.warning("Investigador: fragmento de política inválido")
    try:
        return ResearchArtifact(
            consulta=str(ultima.get("consulta") or ""),
            producto=producto,
            findings=list(textos.values()),
            fuentes=list(textos),
            fragmentos=fragmentos,
            muestra=muestra,
            confidence=0.9 if muestra >= settings.minimo_resenas else 0.45,
        )
    except ValidationError as exc:
        logger.warning("Investigador: artefacto inválido: %s", exc)
        return None


def brief_investigacion(state: AgentState) -> str:
    """Solo el pedido y el tamaño de la parcela. No pasa el análisis ni el historial."""
    research = leer_investigacion(state.get("research"))
    muestra = research.muestra if research is not None else 0
    pedido = _pedido(state)
    return (
        f"pedido: {pedido}\n"
        f"muestra_actual: {muestra}\n"
        f"minimo_resenas: {settings.minimo_resenas}"
    )


def _pedido(state: AgentState) -> str:
    for message in state["messages"]:
        if message.type == "human" and isinstance(message.content, str):
            return message.content
    return ""


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


def build_investigador(model: BaseChatModel | Runnable[Any, Any]):
    agent = create_react_agent(model, [buscar_conocimiento, buscar_resenas, obtener_resena], prompt=PROMPT)

    async def investigador_node(state: AgentState) -> dict[str, Any]:
        try:
            result = await agent.ainvoke({"messages": [HumanMessage(content=brief_investigacion(state))]})
        except Exception as exc:
            logger.warning("Investigador: el ReAct falló: %s", exc)
            return {
                "messages": [AIMessage(content=f"Investigación interrumpida: {exc}", name="Investigador")]
            }
        child = list(result["messages"])
        artifact = armar_investigacion(child)
        if artifact is None:
            return {
                "messages": [
                    AIMessage(
                        content="No pude dejar una investigación válida.",
                        name="Investigador",
                    )
                ]
            }
        cierre = AIMessage(
            content=(
                f"Investigación: consulta={artifact.consulta}, producto={artifact.producto}, "
                f"muestra={artifact.muestra}, confidence={artifact.confidence}, "
                f"fuentes={', '.join(artifact.fuentes)}."
            ),
            name="Investigador",
        )
        return {
            "messages": _mensajes_de_herramientas(child, cierre),
            "research": artifact.model_dump(),
        }

    return investigador_node
