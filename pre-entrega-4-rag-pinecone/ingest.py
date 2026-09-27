"""Ingesta por lotes: Markdown -> chunks -> embeddings -> Pinecone."""

from __future__ import annotations

import argparse
import sys

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from config import settings
from documents import chunk_id, load_chunks
from pinecone_index import ensure_index


def embeddings() -> OpenAIEmbeddings:
    settings.require_cloud_credentials()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        api_key=settings.openai_api_key,
    )


def vector_store(index=None) -> PineconeVectorStore:
    return PineconeVectorStore(
        index=index or ensure_index(),
        embedding=embeddings(),
        namespace=settings.namespace,
        text_key="text",
    )


def _existing_ids(index, ids: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(ids), settings.upsert_batch_size):
        batch = ids[start : start + settings.upsert_batch_size]
        response = index.fetch(ids=batch, namespace=settings.namespace)
        vectors = getattr(response, "vectors", None) or {}
        found.update(vectors.keys())
    return found


def ingest_documents(*, rebuild: bool = False) -> int:
    """Sube el corpus al namespace. Reusa vectores ya presentes salvo --rebuild."""
    chunks = load_chunks()
    ids = [
        chunk_id(
            chunk.metadata["document_id"],
            int(chunk.metadata["chunk_index"]),
            chunk.page_content,
        )
        for chunk in chunks
    ]
    index = ensure_index()

    if rebuild:
        print(f"Borrando el namespace '{settings.namespace}' antes de reindexar.")
        index.delete(delete_all=True, namespace=settings.namespace)
        pending = list(range(len(chunks)))
    else:
        present = _existing_ids(index, ids)
        pending = [position for position, item_id in enumerate(ids) if item_id not in present]
        print(
            f"Chunks del corpus: {len(chunks)}. "
            f"Ya persistidos: {len(chunks) - len(pending)}. "
            f"Pendientes: {len(pending)}."
        )

    if not pending:
        print("La ingesta no se repite: el namespace ya tiene estos chunks.")
        return 0

    store = vector_store(index)
    written = 0
    for start in range(0, len(pending), settings.upsert_batch_size):
        positions = pending[start : start + settings.upsert_batch_size]
        store.add_documents(
            [chunks[position] for position in positions],
            ids=[ids[position] for position in positions],
            namespace=settings.namespace,
        )
        written += len(positions)
        print(f"Upsert de lote: {written}/{len(pending)} chunks.")

    print(
        "Ingesta completa. El texto original quedó en el metadato 'text', "
        "junto con source, page, category y document_id."
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea el índice serverless, si hace falta, e ingesta el corpus."
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Borra el namespace y vuelve a embeber todos los chunks.",
    )
    args = parser.parse_args()
    try:
        ingest_documents(rebuild=args.rebuild)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error de ingesta: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
