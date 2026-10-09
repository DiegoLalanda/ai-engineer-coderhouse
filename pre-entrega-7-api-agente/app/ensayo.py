"""Modelo determinista. Sigue la rúbrica del módulo 6 y pausa si hay que publicar."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ModeloEnsayo(BaseChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> ModeloEnsayo:
        return self

    @property
    def _llm_type(self) -> str:
        return "ensayo"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decidir(list(messages)))])

    async def _agenerate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)

    def _decidir(self, messages: list[BaseMessage]) -> AIMessage:
        system = _system(messages)
        if "Sos el supervisor" in system:
            return _ruta_supervisor(_last_human(messages))
        if "Sos el investigador" in system:
            return _ruta_investigador(messages)
        if "Sos el analista" in system:
            return _ruta_analista(messages)
        return AIMessage(content="FINALIZAR")


def _ruta_supervisor(raw: str) -> AIMessage:
    data = json.loads(raw)
    investigacion = data["investigacion"]
    analisis = data["analisis"]
    if data["pasos"] > data["tope"]:
        return AIMessage(content="FINALIZAR")
    if investigacion is None:
        return AIMessage(content="Investigador")
    if analisis is None:
        return AIMessage(content="Analista")
    if not analisis["suficiente"]:
        if investigacion["muestra"] > analisis["muestra"]:
            return AIMessage(content="Analista")
        return AIMessage(content="Investigador")
    if analisis["destacar"] and data.get("aprobado") is None:
        return AIMessage(content="Aprobacion")
    return AIMessage(content="FINALIZAR")


def _ruta_investigador(messages: list[BaseMessage]) -> AIMessage:
    brief = _last_human(messages)
    produced = _tools_since_human(messages)
    names = [message.name for message in produced]
    if "buscar_resenas" not in names:
        consulta = "batería" if "muestra_actual: 0" in brief else "Notebook 14"
        return _call("buscar_resenas", {"consulta": consulta}, f"call-buscar-{consulta}")
    if "muestra_actual: 0" not in brief and "obtener_resena" not in names:
        payload = json.loads(produced[-1].content)
        return _call("obtener_resena", {"resena_id": payload["resultados"][0]["id"]}, "call-obtener")
    return AIMessage(content="Listo.")


def _ruta_analista(messages: list[BaseMessage]) -> AIMessage:
    produced = _tools_since_human(messages)
    if any(message.name == "calcular_sentimiento" for message in produced):
        return AIMessage(content="Listo.")
    datos = json.loads(_last_human(messages).split("DATOS:", 1)[1])
    return _call(
        "calcular_sentimiento",
        {
            "producto": datos["producto"],
            "textos": datos["textos"],
            "umbral": datos["umbral"],
            "minimo_resenas": datos["minimo_resenas"],
        },
        "call-sentimiento",
    )


def _call(name: str, args: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def _system(messages: list[BaseMessage]) -> str:
    for message in messages:
        if message.type == "system" and isinstance(message.content, str):
            return message.content
    return ""


def _last_human(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if message.type == "human" and isinstance(message.content, str):
            return message.content
    return ""


def _tools_since_human(messages: list[BaseMessage]) -> list[BaseMessage]:
    collected: list[BaseMessage] = []
    for message in reversed(messages):
        if message.type == "human":
            break
        if message.type == "tool":
            collected.append(message)
    collected.reverse()
    return collected
