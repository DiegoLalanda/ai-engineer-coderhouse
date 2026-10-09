"""Worker. Saca un trabajo de Redis y corre el grafo fuera del request."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app import jobs
from app.observability import tramo
from app.settings import settings

logger = logging.getLogger("intelligence.worker")


async def loop(app) -> None:
    cliente = app.state.redis
    while True:
        item = await cliente.blpop(jobs.QUEUE, timeout=1)
        if item is None:
            continue
        _cola, crudo = item
        try:
            mensaje = json.loads(crudo)
            await procesar(app, mensaje)
        except Exception:
            logger.exception("El worker no pudo procesar %s.", crudo)


async def procesar(app, mensaje: dict) -> None:
    job_id = str(mensaje["job_id"])
    cliente = app.state.redis
    grafo = app.state.graph
    config = {"configurable": {"thread_id": job_id}, "recursion_limit": settings.recursion_limit}
    with tramo("tarea", job_id=job_id, tipo=str(mensaje.get("type", ""))):
        try:
            await jobs.marcar(cliente, job_id, "running")
            if mensaje.get("type") == "resume":
                decision = "si" if mensaje.get("decision") == "si" else "no"
                await grafo.ainvoke(Command(resume=decision), config)
            else:
                estado = await jobs.leer(cliente, job_id)
                if estado is None:
                    return
                await grafo.ainvoke({"messages": [HumanMessage(content=estado.query)]}, config)
            await _cerrar(cliente, grafo, job_id, config)
        except Exception as exc:
            logger.exception("El trabajo %s falló.", job_id)
            await jobs.marcar(cliente, job_id, "failed", error=str(exc))


async def _cerrar(cliente, grafo, job_id: str, config: dict) -> None:
    snapshot = await grafo.aget_state(config)
    if snapshot.next:
        payload = _interrupcion(snapshot)
        await jobs.marcar(cliente, job_id, "waiting_approval", approval=payload, approval_set=True)
        return
    await jobs.marcar(cliente, job_id, "completed", result=_resultado(snapshot), approval_set=True, approval=None)


def _interrupcion(snapshot) -> dict:
    for task in snapshot.tasks or []:
        for item in getattr(task, "interrupts", ()) or []:
            valor = getattr(item, "value", None)
            if isinstance(valor, dict):
                return valor
    return {"pregunta": "¿Aprobar la acción pendiente?"}


def _resultado(snapshot) -> str:
    values = snapshot.values or {}
    for message in reversed(values.get("messages") or []):
        if isinstance(message, AIMessage) and message.content:
            return str(message.content)
    return ""
