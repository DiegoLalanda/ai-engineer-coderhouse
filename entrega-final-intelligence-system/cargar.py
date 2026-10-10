"""Dispara las 5 peticiones concurrentes contra la API ya levantada.

    python cargar.py
"""

from __future__ import annotations

import asyncio
import os

import httpx

from app.graph import PEDIDO_DEMO

API = os.environ.get("API_URL", "http://127.0.0.1:8000")


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=30) as client:
        respuestas = await asyncio.gather(
            *[client.post("/tasks", json={"query": PEDIDO_DEMO}) for _ in range(5)]
        )
    for respuesta in respuestas:
        print(respuesta.status_code, respuesta.text)


if __name__ == "__main__":
    asyncio.run(main())
