"""Mini-script asíncrono con caso normal y prueba de estrés ambigua."""

from __future__ import annotations

import asyncio
import logging
import sys

from chain import PipelineError, process_text
from settings import settings

EXAMPLES = [
    (
        "Incidente crítico",
        """
        La API de pagos construida con FastAPI devuelve HTTP 503 en producción.
        Redis alcanzó 98 % de memoria y el pool de conexiones de PostgreSQL está
        agotado. Desde las 14:30, ningún cliente puede completar una compra.
        """,
    ),
    (
        "Texto ambiguo",
        """
        Desde ayer el servicio responde más lento en algunos momentos. No hay
        métricas, logs ni herramientas identificadas y todavía no se confirmó
        impacto para los usuarios.
        """,
    ),
]


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    for label, text in EXAMPLES:
        print(f"\n=== {label} ===")
        try:
            result = await process_text(text)
        except (PipelineError, TypeError, ValueError) as exc:
            print(f"Error controlado: {type(exc).__name__}: {exc}")
            continue
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.run(main())
