"""Unified Async LLM Client.

Capa de abstracción asíncrona para consumir OpenAI y Anthropic bajo una
interfaz común, con validación Pydantic, streaming y manejo de errores.
"""

from .schemas import ChatMessage, LLMConfig, ModelResponse
from .errors import LLMClientError
from .manager import AsyncLLMManager

__all__ = [
    "ChatMessage",
    "LLMConfig",
    "ModelResponse",
    "LLMClientError",
    "AsyncLLMManager",
]
