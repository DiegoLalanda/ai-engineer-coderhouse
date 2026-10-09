"""Corrida con ChatOpenAI. Escribe la traza de delegación en evidencia/."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from langchain_openai import ChatOpenAI

from graph import build_graph
from settings import BASE_DIR, settings
from trace import correr, render_log

EVIDENCE_DIR = BASE_DIR / "evidencia"
TRACE_PATH = EVIDENCE_DIR / "traza_delegacion.json"
LOG_PATH = EVIDENCE_DIR / "traza_delegacion.log"


def guardar(trace: dict[str, object]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG_PATH.write_text(render_log(trace), encoding="utf-8")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.require_openai_api_key(),
        temperature=0,
        timeout=settings.openai_timeout_seconds,
        max_retries=2,
    )
    app = build_graph(model)
    trace = await correr(app, modelo=settings.openai_model, generador="main.py")
    guardar(trace)
    print(render_log(trace))
    print(f"Traza: {TRACE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
