"""Esquemas Pydantic del Unified Async LLM Client.

Definir esto primero evita el clásico "error de diccionarios anidados":
en vez de pasar dicts sueltos entre funciones, todo el flujo (mensajes de
entrada, configuración del modelo y respuesta) está tipado y validado.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["openai", "anthropic"]
Role = Literal["system", "user", "assistant"]


def usage_as_ints(usage: Any) -> dict[str, int] | None:
    """Normaliza el usage del SDK a `dict[str, int]`.

    Los SDKs actuales (openai 3.x, anthropic 1.x) meten objetos anidados
    (`prompt_tokens_details`, `output_tokens_details`, ...). Si se hace
    `model_dump()` crudo, Pydantic rechaza `ModelResponse.usage`.
    """
    if usage is None:
        return None
    raw = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if not isinstance(raw, dict):
        return None
    ints = {str(key): value for key, value in raw.items() if isinstance(value, int)}
    return ints or None


class ChatMessage(BaseModel):
    """Un mensaje individual del historial de chat (formato agnóstico de proveedor)."""

    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = Field(min_length=1, description="Texto del mensaje. No puede ir vacío.")


class LLMConfig(BaseModel):
    """Configuración de una llamada al modelo.

    Corrección aplicada respecto a la entrega anterior: el modelo de lenguaje
    (`model`) ahora es un parámetro configurable en lugar de estar
    hardcodeado ("gpt-4o-mini" / "claude-3-5-sonnet-latest") dentro de cada
    cliente.
    """

    provider: Provider
    model: str = Field(description='Ej: "gpt-4o-mini" (OpenAI) o "claude-3-5-sonnet-latest" (Anthropic).')
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0, le=8192)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    timeout_s: float = Field(default=30.0, gt=0.0, description="Timeout por llamada, generate y stream (asyncio.timeout).")
    max_retries: int = Field(default=2, ge=0, le=5, description="Reintentos ante errores transitorios (rate limit, red).")
    max_concurrency: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Tope de llamadas simultáneas (asyncio.Semaphore) para no disparar 429.",
    )


class ModelResponse(BaseModel):
    """Respuesta unificada, independiente del proveedor.

    Normaliza las diferencias entre SDKs (OpenAI expone `choices[0].message`,
    Anthropic expone una lista de bloques en `content`) para que el resto de
    la app nunca dependa de un string suelto ni de la forma interna de cada
    SDK.
    """

    provider: Provider
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    latency_s: float | None = None
    is_error: bool = False
    raw_error: str | None = Field(default=None, description="Detalle del error si is_error=True.")

    def __str__(self) -> str:  # pragma: no cover - conveniencia para prints/logs
        tag = "ERROR" if self.is_error else "OK"
        return f"[{self.provider}:{self.model}][{tag}] {self.content}"


__all__ = ["Provider", "Role", "ChatMessage", "LLMConfig", "ModelResponse", "usage_as_ints"]
