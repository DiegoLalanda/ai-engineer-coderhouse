"""Variables de entorno. La API key no se versiona."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    recursion_limit: int = Field(default=10, ge=2, le=25)
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    checkpoint_db: Path = BASE_DIR / "data" / "checkpoints.sqlite"
    orders_db: Path = BASE_DIR / "data" / "pedidos.sqlite"

    @field_validator("checkpoint_db", "orders_db")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            return (BASE_DIR / value).resolve()
        return value

    def require_openai_api_key(self) -> str:
        if self.openai_api_key is None:
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Copiá .env.example a .env y completá la clave."
            )
        value = self.openai_api_key.get_secret_value().strip()
        if not value or "..." in value:
            raise RuntimeError(
                "OPENAI_API_KEY sigue siendo el valor de ejemplo. Completala en .env."
            )
        return value


settings = Settings()
