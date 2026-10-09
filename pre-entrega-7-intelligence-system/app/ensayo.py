"""Modelo determinista para la verificación. Sigue la rúbrica y llama a las herramientas reales."""

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
    if investigacion is None:
        return AIMessage(content="Investigador")
    if investigacion["muestra"] > 0 and analisis is None:
        return AIMessage(content="Analista")
    if analisis is not None and analisis["destacar"] and data["aprobado"] is None:
        return AIMessage(content="Aprobacion")
    return AIMessage(content="FINALIZAR")


def _ruta_investigador(messages: list[BaseMessage]) -> AIMessage:
    brief = _last_human(messages)
    produced = _tools_since_human(messages)
    names = [message.name for message in produced]
    consulta = brief.split("pedido:", 1)[-1].strip() or brief
    if "buscar_conocimiento" not in names:
        return _call("buscar_conocimiento", {"consulta": consulta}, "call-conocimiento")
    if "buscar_resenas" not in names:
        return _call("buscar_resenas", {"consulta": consulta}, "call-resenas")
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
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


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
