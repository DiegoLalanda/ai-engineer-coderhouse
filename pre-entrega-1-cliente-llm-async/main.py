"""
Script de validación — Pre-entrega 1: Cliente de LLM robusto y asíncrono
Curso AI Engineer — Coderhouse (Módulo 1)

Carga el .env, arma un AsyncLLMManager por proveedor disponible (según qué
API keys estén configuradas) y prueba modo normal y modo streaming con la
pregunta "¿Qué es la entropía?".

Ejecutar:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

from llm_client import AsyncLLMManager, ChatMessage, LLMConfig
from llm_client.settings import Settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

PREGUNTA = "¿Qué es la entropía?"


def _build_messages() -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="Respondé en español, en un párrafo breve y claro."),
        ChatMessage(role="user", content=PREGUNTA),
    ]


async def probar_modo_normal(manager: AsyncLLMManager, provider: str) -> None:
    logger.info("%-10s | modo normal | pregunta=%r", provider, PREGUNTA)
    respuesta = await manager.generate(_build_messages())
    if respuesta.is_error:
        logger.error("%-10s | ERROR controlado -> %s", provider, respuesta.raw_error)
    else:
        logger.info(
            "%-10s | OK en %.2fs | %s",
            provider,
            respuesta.latency_s or 0.0,
            respuesta.content.strip().replace("\n", " "),
        )


async def probar_modo_streaming(manager: AsyncLLMManager, provider: str) -> None:
    logger.info("%-10s | modo streaming | pregunta=%r", provider, PREGUNTA)
    print(f"[{provider}] ", end="", flush=True)
    async for fragmento in manager.stream(_build_messages()):
        print(fragmento, end="", flush=True)
    print()  # salto de línea final


async def probar_proveedor(config: LLMConfig, settings: Settings) -> None:
    try:
        manager = AsyncLLMManager(config, settings)
    except Exception as exc:  # instanciación falló (ej. falta API key)
        logger.error("%-10s | no se pudo inicializar el cliente -> %s", config.provider, exc)
        return

    await probar_modo_normal(manager, config.provider)
    await probar_modo_streaming(manager, config.provider)


async def main() -> None:
    load_dotenv()  # también soportado nativamente por pydantic-settings (env_file=".env")
    settings = Settings()

    candidatos: list[LLMConfig] = []
    if settings.openai_api_key is not None:
        candidatos.append(LLMConfig(provider="openai", model=settings.default_model_for("openai")))
    else:
        logger.warning("openai     | OPENAI_API_KEY no configurada, se omite la prueba")

    if settings.anthropic_api_key is not None:
        candidatos.append(LLMConfig(provider="anthropic", model=settings.default_model_for("anthropic")))
    else:
        logger.warning("anthropic  | ANTHROPIC_API_KEY no configurada, se omite la prueba")

    if not candidatos:
        logger.error("No hay ninguna API key configurada. Copiá .env.example a .env y completá al menos una.")
        return

    # gather: si hay dos proveedores, corren en paralelo. return_exceptions=True
    # evita que un fallo tumbe al otro (mismo patrón de la teoría del módulo 1).
    resultados = await asyncio.gather(
        *(probar_proveedor(config, settings) for config in candidatos),
        return_exceptions=True,
    )
    for resultado in resultados:
        if isinstance(resultado, Exception):
            logger.error("proveedor falló de forma inesperada -> %s", resultado)

    logger.info("Validación finalizada.")


if __name__ == "__main__":
    asyncio.run(main())
