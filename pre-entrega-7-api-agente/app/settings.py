"""Configuración. El modelo, Redis y Phoenix salen del entorno."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    prompt_template_version: str = Field(default="2026-10-09", validation_alias="PROMPT_TEMPLATE_VERSION")
    recursion_limit: int = Field(default=30, validation_alias="RECURSION_LIMIT")
    max_steps: int = Field(default=8, validation_alias="MAX_STEPS")
    openai_timeout_seconds: float = Field(default=40.0, validation_alias="OPENAI_TIMEOUT_SECONDS")

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    checkpoint_backend: str = Field(default="redis", validation_alias="CHECKPOINT_BACKEND")
    sqlite_path: Path = Field(
        default=BASE_DIR / "data" / "checkpoints.sqlite",
        validation_alias="SQLITE_PATH",
    )

    phoenix_collector_endpoint: str = Field(default="", validation_alias="PHOENIX_COLLECTOR_ENDPOINT")
    phoenix_project_name: str = Field(default="api-agente", validation_alias="PHOENIX_PROJECT_NAME")
    force_ensayo: bool = Field(default=False, validation_alias="FORCE_ENSAYO")

    corpus_dir: Path = BASE_DIR / "data" / "resenas"
    evidencia_dir: Path = BASE_DIR / "evidencia"
    umbral_destacado: float = 0.7
    minimo_resenas: int = 2


settings = Settings()
