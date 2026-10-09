"""Configuración. Ningún modelo, índice ni puerto queda escrito en la lógica."""

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
    request_timeout_s: float = Field(default=40.0, validation_alias="REQUEST_TIMEOUT_S")

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    checkpoint_backend: str = Field(default="sqlite", validation_alias="CHECKPOINT_BACKEND")
    sqlite_path: Path = Field(
        default=BASE_DIR / "data" / "checkpoints.sqlite",
        validation_alias="SQLITE_PATH",
    )

    chroma_path: str = Field(default="", validation_alias="CHROMA_PATH")
    chroma_collection: str = Field(default="conocimiento", validation_alias="CHROMA_COLLECTION")
    embedding_provider: str = Field(default="local", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL")
    retrieval_top_k: int = Field(default=2, validation_alias="RETRIEVAL_TOP_K")

    phoenix_collector_endpoint: str = Field(default="", validation_alias="PHOENIX_COLLECTOR_ENDPOINT")
    force_ensayo: bool = Field(default=False, validation_alias="FORCE_ENSAYO")

    corpus_dir: Path = BASE_DIR / "data" / "resenas"
    conocimiento_dir: Path = BASE_DIR / "data" / "politicas"
    umbral_sentimiento: float = 0.7
    minimo_resenas: int = 2
    evidencia_dir: Path = BASE_DIR / "evidencia"


settings = Settings()
