"""Armado de la traza de delegación."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from graph import PEDIDO_DEMO
from settings import settings
from state import AgentState, AnalysisArtifact, ResearchArtifact


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
                events.append(
                    {
                        "tipo": "agente",
                        "nombre": getattr(message, "name", None) or "ai",
                        "content": text,
                    }
                )
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


def _parcela(value: ResearchArtifact | AnalysisArtifact | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return value.model_dump()


def render_log(trace: dict[str, Any]) -> str:
    lines = [
        f"modelo: {trace['modelo']}",
        f"generador: {trace['generador']}",
        f"pasos: {trace['steps']}",
        f"task_completed: {trace['task_completed']}",
        f"recursion_limit: {trace['recursion_limit']}",
        "",
        f"Pedido: {trace['pedido']}",
        "",
    ]
    for event in trace["eventos"]:
        kind = event["tipo"]
        if kind == "human":
            lines.append(f"Usuario: {event['content']}")
        elif kind == "tool_call":
            args = json.dumps(event["args"], ensure_ascii=False)
            lines.append(f"-> {event['nombre']}({args})")
        elif kind == "tool_result":
            lines.append(f"<- {event['nombre']}: {event['content']}")
        elif kind == "agente":
            lines.append(f"{event['nombre']}: {event['content']}")
    lines.append("")
    lines.append("research: " + json.dumps(trace["research"], ensure_ascii=False))
    lines.append("analysis: " + json.dumps(trace["analysis"], ensure_ascii=False))
    return "\n".join(lines).rstrip() + "\n"


async def correr(
    app: CompiledStateGraph[AgentState, Any, AgentState, AgentState],
    *,
    modelo: str,
    generador: str,
    pedido: str = PEDIDO_DEMO,
) -> dict[str, Any]:
    result = await app.ainvoke(
        {"messages": [HumanMessage(content=pedido)]},
        {"recursion_limit": settings.recursion_limit},
    )
    messages = list(result["messages"])
    return {
        "modelo": modelo,
        "generador": generador,
        "pedido": pedido,
        "recursion_limit": settings.recursion_limit,
        "steps": result.get("steps"),
        "next": result.get("next"),
        "task_completed": result.get("task_completed"),
        "research": _parcela(result.get("research")),
        "analysis": _parcela(result.get("analysis")),
        "eventos": eventos_de(messages),
    }
