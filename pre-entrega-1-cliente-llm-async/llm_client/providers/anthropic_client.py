"""Cliente asíncrono para Anthropic.

Usa `AsyncAnthropic` y normaliza dos diferencias clave frente a OpenAI:
1) el prompt de sistema va aparte (`system=...`), no dentro de `messages`.
2) el texto de respuesta viene en una lista de bloques (`content`), no en
   un string plano como `choices[0].message.content`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)

from ..base_client import BaseLLMClient
from ..errors import ConfigurationError, LLMClientError
from ..schemas import ChatMessage, LLMConfig, ModelResponse, usage_as_ints
from ..settings import Settings


class AnthropicClient(BaseLLMClient):
    def __init__(self, config: LLMConfig, settings: Settings) -> None:
        super().__init__(config)
        api_key = settings.api_key_for("anthropic")
        if api_key is None:
            raise ConfigurationError("anthropic", "Falta ANTHROPIC_API_KEY en el entorno/.env", retryable=False)
        self._client = AsyncAnthropic(api_key=api_key.get_secret_value())

    @staticmethod
    def _split_messages(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
        """Anthropic no acepta role='system' dentro de `messages`: va en `system=`."""
        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        system = "\n".join(system_parts) if system_parts else None
        return system, chat_messages

    def _sampling_kwargs(self) -> dict[str, dict[str, float]]:
        """`temperature`/`top_p` vía `extra_body`.

        El SDK oficial de Anthropic instalado en este proyecto ya no expone
        `temperature` ni `top_p` como parámetros tipados en
        `messages.create()` / `messages.stream()` (verificado por
        introspección de la firma real del SDK instalado). `extra_body` los
        mergea igualmente en el JSON crudo que se envía a la API, así que la
        configuración sigue siendo efectiva sin romper la llamada con un
        `TypeError` por keyword argument inesperado.
        """
        return {"extra_body": {"temperature": self.config.temperature, "top_p": self.config.top_p}}

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        system, chat_messages = self._split_messages(messages)
        inicio = time.perf_counter()
        try:
            async with asyncio.timeout(self.config.timeout_s):
                response = await self._client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=chat_messages,
                    **self._sampling_kwargs(),
                )
            # content es una lista de bloques (TextBlock, ToolUseBlock, ...);
            # unificamos concatenando solo el texto.
            text = "".join(block.text for block in response.content if block.type == "text")
            usage = usage_as_ints(response.usage)
            return ModelResponse(
                provider="anthropic",
                model=response.model,
                content=text,
                finish_reason=response.stop_reason,
                usage=usage,
                latency_s=time.perf_counter() - inicio,
            )
        except TimeoutError as exc:
            raise LLMClientError("anthropic", f"Timeout local de {self.config.timeout_s}s superado", retryable=True) from exc
        except RateLimitError as exc:
            raise LLMClientError("anthropic", f"Rate limit alcanzado: {exc}", retryable=True) from exc
        except AuthenticationError as exc:
            raise LLMClientError("anthropic", f"API key inválida o sin permisos: {exc}", retryable=False) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMClientError("anthropic", f"Error de red/timeout de la API: {exc}", retryable=True) from exc
        except APIError as exc:
            raise LLMClientError("anthropic", f"Error de la API de Anthropic: {exc}", retryable=False) from exc

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        system, chat_messages = self._split_messages(messages)
        try:
            async with asyncio.timeout(self.config.timeout_s):
                async with self._client.messages.stream(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=chat_messages,
                    **self._sampling_kwargs(),
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
        except TimeoutError as exc:
            raise LLMClientError(
                "anthropic",
                f"Timeout local de {self.config.timeout_s}s superado durante streaming",
                retryable=True,
            ) from exc
        except RateLimitError as exc:
            raise LLMClientError("anthropic", f"Rate limit alcanzado durante streaming: {exc}", retryable=True) from exc
        except AuthenticationError as exc:
            raise LLMClientError("anthropic", f"API key inválida o sin permisos: {exc}", retryable=False) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMClientError("anthropic", f"Error de red/timeout durante streaming: {exc}", retryable=True) from exc
        except APIError as exc:
            raise LLMClientError("anthropic", f"Error de la API de Anthropic durante streaming: {exc}", retryable=False) from exc


__all__ = ["AnthropicClient"]
