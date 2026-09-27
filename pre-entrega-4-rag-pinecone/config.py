"""Configuración del índice serverless y del corpus NimbusQueue."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _path_from_env(variable: str, default: Path) -> Path:
    raw_value = os.getenv(variable)
    path = Path(raw_value).expanduser() if raw_value else default
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = _path_from_env("RAG_DATA_DIR", BASE_DIR / "data")
    golden_set_path: Path = _path_from_env(
        "GOLDEN_SET_PATH", BASE_DIR / "data" / "golden_set.json"
    )
    pinecone_api_key: str | None = os.getenv("PINECONE_API_KEY") or None
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    index_name: str = os.getenv("INDEX_NAME", "nimbus-rag")
    namespace: str = os.getenv("PINECONE_NAMESPACE", "nimbus-docs")
    cloud: str = os.getenv("PINECONE_CLOUD", "aws")
    region: str = os.getenv("PINECONE_REGION", "us-east-1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    metric: str = "cosine"
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "600"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "80"))
    top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    upsert_batch_size: int = int(os.getenv("UPSERT_BATCH_SIZE", "100"))
    token_encoding: str = "cl100k_base"

    def require_cloud_credentials(self) -> None:
        missing = [
            name
            for name, value in (
                ("PINECONE_API_KEY", self.pinecone_api_key),
                ("OPENAI_API_KEY", self.openai_api_key),
                ("INDEX_NAME", self.index_name),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Faltan variables: "
                + ", ".join(missing)
                + ". Copiá .env.example a .env y completá las claves."
            )

    def validate(self) -> None:
        if not 500 <= self.chunk_size <= 800:
            raise ValueError("CHUNK_SIZE debe estar entre 500 y 800 tokens.")
        if not 0 < self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP debe ser mayor que 0 y menor que CHUNK_SIZE.")
        if self.top_k != 5:
            raise ValueError("RAG_TOP_K debe ser 5: la rúbrica evalúa Precision@5 y Recall@5.")
        if self.embedding_dimension != 1536:
            raise ValueError(
                "EMBEDDING_DIMENSION debe ser 1536 para text-embedding-3-small."
            )
        if not 50 <= self.upsert_batch_size <= 200:
            raise ValueError("UPSERT_BATCH_SIZE debe estar entre 50 y 200.")
        if not self.namespace.strip():
            raise ValueError("PINECONE_NAMESPACE no puede estar vacío.")
        if not self.index_name.strip():
            raise ValueError("INDEX_NAME no puede estar vacío.")


settings = Settings()
settings.validate()
