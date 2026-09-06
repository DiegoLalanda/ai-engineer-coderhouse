"""Clase base abstracta común a todos los proveedores.

Aplica el mismo espíritu del Factory Pattern señalado como punto fuerte en
la devolución anterior: cualquier proveedor nuevo solo necesita heredar de
`BaseLLMClient` e implementar `generate` y `stream` para poder conectarse
al `AsyncLLMManager` sin tocar el resto de la aplicación (Intercambiabilidad).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .schemas import ChatMessage, LLMConfig, ModelResponse


class BaseLLMClient(ABC):
    """Interfaz común: toda llamada es asíncrona (async/await), nunca bloqueante."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @abstractmethod
    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        """Devuelve la respuesta completa del modelo (modo no-streaming)."""
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Generador asíncrono: entrega fragmentos de texto a medida que llegan."""
        raise NotImplementedError


__all__ = ["BaseLLMClient"]
