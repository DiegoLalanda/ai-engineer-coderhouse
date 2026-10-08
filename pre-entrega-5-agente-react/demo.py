"""Corrida con ChatOpenAI. Escribe la traza ReAct en evidencia/."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph import build_graph
from session import Turno, correr_turnos, render_log
from settings import BASE_DIR, settings

EVIDENCE_DIR = BASE_DIR / "evidencia"
TRACE_PATH = EVIDENCE_DIR / "traza_react.json"
LOG_PATH = EVIDENCE_DIR / "traza_react.log"

THREAD_PRINCIPAL = "sesion-102"
THREAD_NUEVA = "sesion-vacia"
THREAD_ERROR = "sesion-999"

TURNOS = [
    Turno(
        nombre="razonamiento multi-paso",
        thread_id=THREAD_PRINCIPAL,
        pregunta=(
            "¿Cuántos pedidos tuvo el cliente 102, cuál fue el total "
            "y qué se compró en el último?"
        ),
    ),
    Turno(
        nombre="misma sesion",
        thread_id=THREAD_PRINCIPAL,
        pregunta="¿y el primero?",
    ),
    Turno(
        nombre="otra sesion",
        thread_id=THREAD_NUEVA,
        pregunta="¿y el último?",
    ),
    Turno(
        nombre="error y aclaracion",
        thread_id=THREAD_ERROR,
        pregunta="¿Cuántos pedidos tuvo el cliente 999 y cuál fue el total?",
    ),
]

REANUDAR = [
    Turno(
        nombre="reanudacion de sesion-102",
        thread_id=THREAD_PRINCIPAL,
        pregunta="¿y el primero?",
    )
]


def _print_trace(trace: dict[str, object]) -> None:
    print(render_log(trace))


async def ejecutar(checkpoint: Path, turnos: list[Turno]) -> dict[str, object]:
    # SqliteSaver síncrono no implementa aget_tuple. ainvoke usa AsyncSqliteSaver.
    settings.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.require_openai_api_key(),
        temperature=0,
        timeout=settings.openai_timeout_seconds,
        max_retries=2,
    )
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint)) as checkpointer:
        app = build_graph(checkpointer, model)
        return await correr_turnos(
            app,
            turnos,
            modelo=settings.openai_model,
            generador="demo.py",
        )


def guardar(trace: dict[str, object]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG_PATH.write_text(render_log(trace), encoding="utf-8")


async def main() -> None:
    reanudar = "--reanudar" in sys.argv
    turnos = REANUDAR if reanudar else TURNOS
    trace = await ejecutar(settings.checkpoint_db, turnos)
    guardar(trace)
    _print_trace(trace)
    print(f"Traza: {TRACE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
