"""API. El POST guarda el trabajo y vuelve enseguida. El grafo corre en el worker."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis

from app import jobs
from app.checkpointer import abrir_checkpointer
from app.ensayo import ModeloEnsayo
from app.graph import build_graph
from app.knowledge import indice
from app.observability import configurar
from app.settings import settings
from app.state import AprobacionEntrada, TareaCreada, TareaEntrada, TareaEstado
from app.worker import loop

logger = logging.getLogger("intelligence.api")


def modelo():
    if settings.force_ensayo or not settings.openai_api_key.strip():
        return ModeloEnsayo()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
        timeout=settings.request_timeout_s,
    )


def cliente_redis() -> Redis:
    if settings.redis_url.startswith("fakeredis://"):
        from fakeredis.aioredis import FakeRedis

        return FakeRedis(decode_responses=True)
    return Redis.from_url(settings.redis_url, decode_responses=True)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO)
        configurar()
        indice.cargar()
        app.state.redis = cliente_redis()
        async with abrir_checkpointer() as checkpointer:
            app.state.graph = build_graph(modelo(), checkpointer)
            import asyncio

            tarea = asyncio.create_task(loop(app))
            try:
                yield
            finally:
                tarea.cancel()
                try:
                    await tarea
                except asyncio.CancelledError:
                    pass
                await app.state.redis.aclose()

    app = FastAPI(
        title="Intelligence System",
        version="1.0.0",
        summary="Inteligencia comercial con RAG, supervisor y aprobación humana.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/tasks", response_model=TareaCreada, status_code=202)
    async def crear_tarea(entrada: TareaEntrada) -> TareaCreada:
        job_id = await jobs.crear(app.state.redis, entrada.query)
        return TareaCreada(job_id=job_id, status="pending")

    @app.get("/tasks/{job_id}", response_model=TareaEstado)
    async def leer_tarea(job_id: str) -> TareaEstado:
        estado = await jobs.leer(app.state.redis, job_id)
        if estado is None:
            raise HTTPException(status_code=404, detail="Trabajo inexistente.")
        return estado

    @app.post("/tasks/{job_id}/approve", response_model=TareaEstado)
    async def aprobar(job_id: str, entrada: AprobacionEntrada) -> TareaEstado:
        estado = await jobs.leer(app.state.redis, job_id)
        if estado is None:
            raise HTTPException(status_code=404, detail="Trabajo inexistente.")
        if estado.status != "waiting_approval":
            raise HTTPException(status_code=409, detail="El trabajo no está esperando aprobación.")
        await jobs.pedir_reanudacion(app.state.redis, job_id, entrada.approved)
        return estado

    return app


app = create_app()
