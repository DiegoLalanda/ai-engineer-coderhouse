"""Checkpointer. En producción es RedisSaver; la verificación puede usar SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
