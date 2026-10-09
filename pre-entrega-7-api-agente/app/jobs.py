"""Cola de trabajos. El estado queda en Redis antes de encolar."""

from __future__ import annotations

import json
import uuid

from redis.asyncio import Redis

from app.state import JobStatus, TareaEstado

QUEUE = "tasks_queue"


def clave(job_id: str) -> str:
    return f"status:{job_id}"


async def crear(cliente: Redis, query: str) -> str:
    job_id = str(uuid.uuid4())
    await _guardar(cliente, job_id, query, "pending", "", "")
    await cliente.rpush(QUEUE, json.dumps({"type": "start", "job_id": job_id}))
    return job_id


async def pedir_reanudacion(cliente: Redis, job_id: str, approved: bool) -> None:
    decision = "si" if approved else "no"
    await marcar(cliente, job_id, "pending")
    await cliente.rpush(QUEUE, json.dumps({"type": "resume", "job_id": job_id, "decision": decision}))


async def leer(cliente: Redis, job_id: str) -> TareaEstado | None:
    crudo = await cliente.get(clave(job_id))
    if crudo is None:
        return None
    return TareaEstado.model_validate_json(crudo)


async def marcar(
    cliente: Redis,
    job_id: str,
    status: JobStatus,
    *,
    result: str | None = None,
    error: str | None = None,
    approval: dict | None = None,
    approval_set: bool = False,
) -> TareaEstado:
    actual = await leer(cliente, job_id)
    if actual is None:
        raise KeyError(job_id)
    payload = actual.model_dump()
    payload["status"] = status
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    if approval_set:
        payload["approval"] = approval
    estado = TareaEstado.model_validate(payload)
    await cliente.set(clave(job_id), estado.model_dump_json())
    return estado


async def _guardar(
    cliente: Redis,
    job_id: str,
    query: str,
    status: JobStatus,
    result: str,
    error: str,
) -> None:
    estado = TareaEstado(job_id=job_id, status=status, query=query, result=result, error=error)
    await cliente.set(clave(job_id), estado.model_dump_json())
