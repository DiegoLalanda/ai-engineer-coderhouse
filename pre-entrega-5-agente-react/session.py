"""Corrida de una sesión y armado de la traza ReAct."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from graph import AgentState, config_for
from settings import settings


@dataclass(frozen=True)
class Turno:
    nombre: str
    thread_id: str
    pregunta: str


def _content(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def eventos_de(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for message in messages:
        if message.type == "human":
            events.append({"tipo": "human", "content": _content(message)})
            continue
        if message.type == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                events.append(
                    {
                        "tipo": "tool_call",
                        "nombre": call["name"],
                        "args": call.get("args", {}),
                        "id": call.get("id"),
                    }
                )
            text = _content(message).strip()
            if text and not getattr(message, "tool_calls", None):
                events.append({"tipo": "respuesta", "content": text})
            continue
        if message.type == "tool":
            events.append(
                {
                    "tipo": "tool_result",
                    "nombre": getattr(message, "name", None),
                    "content": _content(message),
                }
            )
    return events


def render_log(trace: dict[str, Any]) -> str:
    lines = [
        f"modelo: {trace['modelo']}",
        f"recursion_limit: {trace['recursion_limit']}",
        f"generador: {trace['generador']}",
        "",
    ]
    for case in trace["casos"]:
        lines.append(f"## {case['nombre']}  thread_id={case['thread_id']}")
        lines.append(f"herramientas_invocadas: {case['herramientas_invocadas']}")
        for event in case["eventos"]:
            kind = event["tipo"]
            if kind == "human":
                lines.append(f"Usuario: {event['content']}")
            elif kind == "tool_call":
                args = json.dumps(event["args"], ensure_ascii=False)
                lines.append(f"-> {event['nombre']}({args})")
            elif kind == "tool_result":
                lines.append(f"<- {event['nombre']}: {event['content']}")
            elif kind == "respuesta":
                lines.append(f"Respuesta: {event['content']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def correr_turnos(
    app: CompiledStateGraph[AgentState, Any, AgentState, AgentState],
    turnos: list[Turno],
    *,
    modelo: str,
    generador: str,
) -> dict[str, Any]:
    seen: dict[str, int] = {}
    cases: list[dict[str, Any]] = []
    for turno in turnos:
        prior = seen.get(turno.thread_id, 0)
        result = await app.ainvoke(
            {"messages": [HumanMessage(content=turno.pregunta)]},
            config_for(turno.thread_id),
        )
        fresh = list(result["messages"][prior:])
        seen[turno.thread_id] = len(result["messages"])
        events = eventos_de(fresh)
        tool_calls = [event for event in events if event["tipo"] == "tool_call"]
        cases.append(
            {
                "nombre": turno.nombre,
                "thread_id": turno.thread_id,
                "pregunta": turno.pregunta,
                "herramientas_invocadas": len(tool_calls),
                "eventos": events,
            }
        )
    return {
        "modelo": modelo,
        "generador": generador,
        "recursion_limit": settings.recursion_limit,
        "casos": cases,
    }
