"""Carga, limpieza y chunking del corpus técnico."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

CATALOG: dict[str, dict[str, str]] = {
    "01_nimbus_client.md": {
        "document_id": "nimbus-client",
        "category": "sdk",
    },
    "02_nimbus_errores.md": {
        "document_id": "nimbus-errores",
        "category": "errores",
    },
    "03_nimbus_config.md": {
        "document_id": "nimbus-config",
        "category": "configuracion",
    },
    "04_nimbus_dlq.md": {
        "document_id": "nimbus-dlq",
        "category": "operaciones",
    },
    "05_nimbus_seguridad.md": {
        "document_id": "nimbus-seguridad",
        "category": "seguridad",
    },
    "06_nimbus_metricas.md": {
        "document_id": "nimbus-metricas",
        "category": "observabilidad",
    },
}

METADATA_KEYS = ("source", "page", "category", "document_id", "chunk_index")


def clean_text(text: str) -> str:
    """Normaliza saltos y espacios sin borrar la estructura Markdown."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def discover_documents(data_dir: Path | None = None) -> list[Path]:
    source_dir = data_dir or settings.data_dir
    files = [
        path
        for path in sorted(source_dir.glob("*.md"))
        if path.name in CATALOG
    ]
    missing = sorted(set(CATALOG) - {path.name for path in files})
    if missing:
        raise FileNotFoundError(
            "Faltan documentos del catálogo: " + ", ".join(missing)
        )
    return files


def _splitter() -> RecursiveCharacterTextSplitter:
    tokenizer = tiktoken.get_encoding(settings.token_encoding)
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=lambda text: len(tokenizer.encode(text)),
        separators=["\n\n", "\n", ". ", ".", " ", ""],
        keep_separator=True,
        strip_whitespace=True,
    )


def chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    """ID estable: el mismo chunk se actualiza con upsert y no se duplica."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{document_id}::{chunk_index}::{digest}"


def load_chunks(data_dir: Path | None = None) -> list[Document]:
    """Fragmenta el corpus y adjunta el esquema fijo de metadatos."""
    splitter = _splitter()
    documents: list[Document] = []
    for path in discover_documents(data_dir):
        spec = CATALOG[path.name]
        raw_text = clean_text(path.read_text(encoding="utf-8"))
        pieces = splitter.split_text(raw_text)
        source = path.name
        for index, piece in enumerate(pieces):
            documents.append(
                Document(
                    page_content=piece,
                    metadata={
                        "source": source,
                        "page": index + 1,
                        "category": spec["category"],
                        "document_id": spec["document_id"],
                        "chunk_index": index,
                    },
                )
            )
    if len(documents) <= settings.top_k:
        raise RuntimeError(
            "El corpus debe producir más chunks que top_k; "
            "si no, Precision@5 no discrimina."
        )
    return documents
