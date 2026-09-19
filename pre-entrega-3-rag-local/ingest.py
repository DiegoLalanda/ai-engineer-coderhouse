"""Ingesta incremental: archivos -> limpieza -> chunks -> ChromaDB."""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import settings
from document_processor import DocumentProcessor
from vector_store import VectorMemoryManager

SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass
class IngestionStats:
    files_found: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    chunks_upserted: int = 0


def discover_documents(data_dir: Path) -> list[Path]:
    """Encuentra documentos compatibles en orden reproducible."""
    return sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def file_hash(path: Path) -> str:
    """Hash del archivo para detectar cambios sin reindexar todo."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_title(raw_text: str, path: Path) -> str:
    """Usa el primer título Markdown o, si no existe, el nombre del archivo."""
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return path.stem.replace("_", " ").replace("-", " ").title()


def metadata_for_chunk(
    *,
    path: Path,
    data_dir: Path,
    title: str,
    content_hash: str,
    chunk_index: int,
    chunk_total: int,
    token_count: int,
) -> dict[str, Any]:
    """Construye el esquema de metadatos común a todos los documentos."""
    return {
        "source": path.relative_to(data_dir).as_posix(),
        "date": datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(),
        "type": "markdown" if path.suffix.lower() == ".md" else "text",
        "title": title,
        "document_hash": content_hash,
        "chunk_index": chunk_index,
        "chunk_total": chunk_total,
        "token_count": token_count,
    }


def ingest_documents(
    data_dir: Path | None = None,
    *,
    rebuild: bool = False,
) -> IngestionStats:
    """Indexa solo archivos nuevos o modificados y limpia fuentes eliminadas."""
    source_dir = (data_dir or settings.data_dir).resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de datos: {source_dir}")

    files = discover_documents(source_dir)
    if not files:
        raise FileNotFoundError(
            f"No se encontraron archivos .txt o .md en {source_dir}"
        )

    processor = DocumentProcessor(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        model_encoding=settings.token_encoding,
    )
    memory = VectorMemoryManager(
        persist_path=settings.persist_dir,
        collection_name=settings.collection_name,
    )
    if rebuild:
        memory.reset_collection()

    stats = IngestionStats(files_found=len(files))
    current_sources = {
        path.relative_to(source_dir).as_posix()
        for path in files
    }

    # Si un archivo fue quitado de /data, también elimina sus vectores obsoletos.
    for stale_source in memory.indexed_sources() - current_sources:
        memory.delete_by_metadata({"source": {"$eq": stale_source}})
        stats.files_deleted += 1

    for path in files:
        source = path.relative_to(source_dir).as_posix()
        content_hash = file_hash(path)

        if not rebuild and memory.source_is_current(source, content_hash):
            print(f"[sin cambios] {source}")
            stats.files_skipped += 1
            continue

        raw_text = path.read_text(encoding="utf-8")
        chunks = processor.process_document(raw_text)
        if not chunks:
            print(f"[vacío]       {source}")
            stats.files_skipped += 1
            continue

        # Evita restos de una versión anterior que tuviera más chunks.
        if source in memory.indexed_sources():
            memory.delete_by_metadata({"source": {"$eq": source}})

        title = document_title(raw_text, path)
        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            ids.append(memory.deterministic_id(source, index, chunk))
            metadatas.append(
                metadata_for_chunk(
                    path=path,
                    data_dir=source_dir,
                    title=title,
                    content_hash=content_hash,
                    chunk_index=index,
                    chunk_total=len(chunks),
                    token_count=processor.calculate_tokens(chunk),
                )
            )

        memory.upsert_documents(ids, chunks, metadatas)
        stats.files_indexed += 1
        stats.chunks_upserted += len(chunks)
        print(f"[indexado]    {source}: {len(chunks)} chunks")

    print(
        "\nResumen: "
        f"{stats.files_indexed} archivos indexados, "
        f"{stats.files_skipped} sin cambios, "
        f"{stats.files_deleted} eliminados, "
        f"{stats.chunks_upserted} chunks escritos. "
        f"Total persistido: {memory.count()} chunks."
    )
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingesta incremental del dataset local en ChromaDB."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Carpeta alternativa con documentos .txt/.md.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Borra la colección y vuelve a indexar todos los documentos.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        ingest_documents(args.data_dir, rebuild=args.rebuild)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error de ingesta: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
