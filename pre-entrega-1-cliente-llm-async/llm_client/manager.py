"""AsyncLLMManager: fachada única sobre OpenAI y Anthropic.

Patrón Factory: en `_PROVIDERS` se registra qué clase concreta corresponde
a cada `provider` de `LLMConfig`. Agregar un tercer proveedor (por ejemplo
Gemini) implica sumar una entrada acá, sin tocar `main.py` ni el resto de
la lógica de negocio (mismo patrón valorado en la devolución anterior,
ahora aplicado a la interfaz `BaseLLMClient`).

Resiliencia: `generate()` reintenta con backoff exponencial los errores
marcados como `retryable` (rate limit, timeout, problemas de red). Un
`asyncio.Semaphore` limita la concurrencia (`max_concurrency`) para no
disparar 429. Si se agotan los reintentos, o el error no es reintentable
(ej. API key inválida), se devuelve un `ModelResponse` con `is_error=True`
en lugar de dejar que la excepción rompa el loop principal del programa.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from .base_client import BaseLLMClient
from .errors import LLMClientError
from .providers.anthropic_client import AnthropicClient
from .providers.openai_client import OpenAIClient
from .schemas import ChatMessage, LLMConfig, ModelResponse
from .settings import Settings

logger = logging.getLogger("llm_client.manager")


class AsyncLLMManager:
    """Punto de entrada único: instancia el proveedor correcto y expone
    `generate()` / `stream()` con la misma firma sin importar quién responda.
    """

    _PROVIDERS: dict[str, type[BaseLLMClient]] = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
    }

    def __init__(self, config: LLMConfig, settings: Settings | None = None) -> None:
        self.config = config
        self.settings = settings or Settings()
        self._client: BaseLLMClient = self._build_client()
        # Tope de llamadas simultáneas: evita un 429 si se dispara un lote con gather.
        self._sem = asyncio.Semaphore(self.config.max_concurrency)

    def _build_client(self) -> BaseLLMClient:
        provider_cls = self._PROVIDERS.get(self.config.provider)
        if provider_cls is None:
            disponibles = ", ".join(self._PROVIDERS)
            raise ValueError(f"Proveedor desconocido: {self.config.provider!r}. Disponibles: {disponibles}")
        return provider_cls(self.config, self.settings)

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        """Respuesta completa (no streaming), con reintentos ante fallas transitorias."""
        async with self._sem:
            delay = 1.0
            last_error: LLMClientError | None = None

            for intento in range(1, self.config.max_retries + 2):  # +1 intento inicial
                try:
                    return await self._client.generate(messages)
                except LLMClientError as exc:
                    last_error = exc
                    if not exc.retryable or intento > self.config.max_retries:
                        logger.error("generate | %s | sin más reintentos (intento %d)", exc, intento)
                        break
                    logger.warning(
                        "generate | %s | reintentando en %.1fs (intento %d/%d)",
                        exc,
                        delay,
                        intento,
                        self.config.max_retries,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2

            assert last_error is not None
            return ModelResponse(
                provider=self.config.provider,
                model=self.config.model,
                content=f"No se pudo obtener respuesta: {last_error.message}",
                finish_reason="error",
                is_error=True,
                raw_error=last_error.message,
            )

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Generador asíncrono de fragmentos de texto.

        Si el proveedor falla a mitad de stream, no se propaga el crash:
        se loguea y se corta el generador de forma prolija (el llamador ya
        recibió los fragmentos previos, que siguen siendo válidos).
        """
        try:
            async with self._sem:
                async with asyncio.timeout(self.config.timeout_s):
                    async for chunk in self._client.stream(messages):
                        yield chunk
        except TimeoutError:
            logger.error(
                "stream | timeout local de %.1fs superado (%s)",
                self.config.timeout_s,
                self.config.provider,
            )
            yield f"\n[ERROR:{self.config.provider}] Timeout local de {self.config.timeout_s}s superado"
        except LLMClientError as exc:
            logger.error("stream | %s", exc)
            yield f"\n[ERROR:{exc.provider}] {exc.message}"


__all__ = ["AsyncLLMManager"]
