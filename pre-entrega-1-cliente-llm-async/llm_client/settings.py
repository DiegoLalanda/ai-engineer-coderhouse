"""Configuración de secretos usando pydantic-settings.

Próximo paso sugerido en la devolución anterior: cargar las API keys desde
variables de entorno / archivo `.env` (en vez de pasarlas a mano), usando
`SecretStr` para que nunca se filtren en logs, prints o representaciones
de error (`repr(settings)` muestra `SecretStr('**********')`).
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Se completa automáticamente desde variables de entorno o `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    # Modelo por defecto por proveedor. Configurable por variable de entorno
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-sonnet-latest"

    def api_key_for(self, provider: str) -> SecretStr | None:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }.get(provider)

    def default_model_for(self, provider: str) -> str:
        return {
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
        }[provider]


__all__ = ["Settings"]
