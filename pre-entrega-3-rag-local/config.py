"""Configuración compartida por la ingesta y la cadena RAG."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _path_from_env(variable: str, default: Path) -> Path:
    """Resuelve rutas configurables sin depender del directorio de ejecución."""
    raw_value = os.getenv(variable)
    path = Path(raw_value).expanduser() if raw_value else default
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    """Valores del proyecto, con defaults seguros para ejecución local."""

    data_dir: Path = _path_from_env("RAG_DATA_DIR", BASE_DIR / "data")
    persist_dir: Path = _path_from_env(
        "CHROMA_PERSIST_DIR", BASE_DIR / "vectorstore"
    )
    collection_name: str = os.getenv(
        "CHROMA_COLLECTION_NAME", "aulanova_knowledge"
    )
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    top_k: int = int(os.getenv("RAG_TOP_K", "4"))
    max_distance: float = float(os.getenv("RAG_MAX_DISTANCE", "0.75"))
    token_encoding: str = os.getenv("TOKEN_ENCODING", "cl100k_base")

    def validate(self) -> None:
        if self.chunk_size < 500:
            raise ValueError("CHUNK_SIZE debe ser de al menos 500 tokens.")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError(
                "CHUNK_OVERLAP debe ser mayor o igual a 0 y menor que CHUNK_SIZE."
            )
        if not 3 <= self.top_k <= 5:
            raise ValueError("RAG_TOP_K debe estar entre 3 y 5.")
        if not 0 < self.max_distance <= 2:
            raise ValueError("RAG_MAX_DISTANCE debe estar entre 0 y 2.")


settings = Settings()
settings.validate()
