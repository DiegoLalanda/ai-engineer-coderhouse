"""Excepciones controladas del Unified Async LLM Client.

Corrección aplicada: en la entrega anterior no había manejo de excepciones
alrededor de los SDKs. Ahora cada proveedor traduce sus errores nativos
(openai.APIError, anthropic.APIError, RateLimitError, etc.) a esta jerarquía
común, marcando además si vale la pena reintentar (`retryable`).
"""

from __future__ import annotations


class LLMClientError(Exception):
    """Error controlado y normalizado, independiente del SDK de origen."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        self.provider = provider
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")


class ConfigurationError(LLMClientError):
    """Falta configuración indispensable (por ejemplo, una API key)."""


__all__ = ["LLMClientError", "ConfigurationError"]
