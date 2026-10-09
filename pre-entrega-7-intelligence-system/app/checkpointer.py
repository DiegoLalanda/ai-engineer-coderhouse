"""Checkpointer del hilo. Redis en el despliegue; SQLite cuando se corre la verificación sin Redis Stack."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.settings import settings


@asynccontextmanager
async def abrir_checkpointer() -> AsyncIterator[BaseCheckpointSaver]:
    if settings.checkpoint_backend.strip().lower() == "redis":
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver

        async with AsyncRedisSaver.from_conn_string(settings.redis_url) as saver:
            await saver.asetup()
            yield saver
        return
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(settings.sqlite_path)) as saver:
        yield saver
