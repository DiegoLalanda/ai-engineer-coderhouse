"""Cliente asíncrono para OpenAI.

Usa `AsyncOpenAI` (nunca el cliente síncrono dentro de una función async,
para no bloquear el event loop) y traduce los errores del SDK
(`openai.APIError` y subclases) a `LLMClientError`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from ..base_client import BaseLLMClient
from ..errors import ConfigurationError, LLMClientError
from ..schemas import ChatMessage, LLMConfig, ModelResponse, usage_as_ints
from ..settings import Settings


class OpenAIClient(BaseLLMClient):
    def __init__(self, config: LLMConfig, settings: Settings) -> None:
        super().__init__(config)
        api_key = settings.api_key_for("openai")
        if api_key is None:
            raise ConfigurationError("openai", "Falta OPENAI_API_KEY en el entorno/.env", retryable=False)
        # SecretStr: la key solo se "desenvuelve" acá, nunca queda en logs.
        self._client = AsyncOpenAI(api_key=api_key.get_secret_value())

    @staticmethod
    def _to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        inicio = time.perf_counter()
        try:
            async with asyncio.timeout(self.config.timeout_s):
                response = await self._client.chat.completions.create(
                    model=self.config.model,
                    messages=self._to_openai_messages(messages),
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    top_p=self.config.top_p,
                )
            choice = response.choices[0]
            usage = usage_as_ints(response.usage)
            return ModelResponse(
                provider="openai",
                model=response.model,
                content=choice.message.content or "",
                finish_reason=choice.finish_reason,
                usage=usage,
                latency_s=time.perf_counter() - inicio,
            )
        except TimeoutError as exc:
            raise LLMClientError("openai", f"Timeout local de {self.config.timeout_s}s superado", retryable=True) from exc
        except RateLimitError as exc:
            raise LLMClientError("openai", f"Rate limit alcanzado: {exc}", retryable=True) from exc
        except AuthenticationError as exc:
            raise LLMClientError("openai", f"API key inválida o sin permisos: {exc}", retryable=False) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMClientError("openai", f"Error de red/timeout de la API: {exc}", retryable=True) from exc
        except APIError as exc:
            raise LLMClientError("openai", f"Error de la API de OpenAI: {exc}", retryable=False) from exc

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        try:
            async with asyncio.timeout(self.config.timeout_s):
                response_stream = await self._client.chat.completions.create(
                    model=self.config.model,
                    messages=self._to_openai_messages(messages),
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    top_p=self.config.top_p,
                    stream=True,
                )
                async for chunk in response_stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        except TimeoutError as exc:
            raise LLMClientError(
                "openai",
                f"Timeout local de {self.config.timeout_s}s superado durante streaming",
                retryable=True,
            ) from exc
        except RateLimitError as exc:
            raise LLMClientError("openai", f"Rate limit alcanzado durante streaming: {exc}", retryable=True) from exc
        except AuthenticationError as exc:
            raise LLMClientError("openai", f"API key inválida o sin permisos: {exc}", retryable=False) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMClientError("openai", f"Error de red/timeout durante streaming: {exc}", retryable=True) from exc
        except APIError as exc:
            raise LLMClientError("openai", f"Error de la API de OpenAI durante streaming: {exc}", retryable=False) from exc


__all__ = ["OpenAIClient"]
