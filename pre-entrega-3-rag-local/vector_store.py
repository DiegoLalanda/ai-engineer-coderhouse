"""Persistencia y operaciones CRUD sobre ChromaDB local."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils import embedding_functions


def build_embedding_function() -> Any:
    """Crea el encoder local usado tanto al indexar como al consultar."""
    return embedding_functions.DefaultEmbeddingFunction()


class VectorMemoryManager:
    """Encapsula una colección persistente y su función de embeddings."""

    def __init__(self, persist_path: Path, collection_name: str) -> None:
        self.persist_path = Path(persist_path)
        self.collection_name = collection_name
        self.persist_path.mkdir(parents=True, exist_ok=True)

        try:
            self.client = chromadb.PersistentClient(path=str(self.persist_path))
            self.collection = self._get_or_create_collection()
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo inicializar ChromaDB en {self.persist_path}: {exc}"
            ) from exc

    def _get_or_create_collection(self) -> Collection:
        return self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=build_embedding_function(),
            metadata={
                "hnsw:space": "cosine",
                "description": "Base local de conocimiento de AulaNova",
            },
        )

    @staticmethod
    def deterministic_id(source: str, chunk_index: int, text: str) -> str:
        """Genera un ID estable a partir del origen, posición y contenido."""
        payload = f"{source}|{chunk_index}|{text}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def reset_collection(self) -> None:
        """Elimina y vuelve a crear la colección conservando la configuración."""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self._get_or_create_collection()
        except Exception as exc:
            raise RuntimeError(f"No se pudo reconstruir la colección: {exc}") from exc

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception as exc:
            raise RuntimeError(f"No se pudo contar la colección: {exc}") from exc

    def upsert_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Crea o actualiza chunks; el ID determinista evita duplicados."""
        if not ids:
            return
        if not (len(ids) == len(documents) == len(metadatas)):
            raise ValueError(
                "ids, documents y metadatas deben tener la misma longitud."
            )

        try:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise RuntimeError(f"No se pudieron persistir los documentos: {exc}") from exc

    def get_by_ids(self, ids: list[str]) -> dict[str, Any]:
        """Lectura exacta por ID."""
        try:
            return self.collection.get(
                ids=ids,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            raise RuntimeError(f"No se pudieron recuperar los IDs: {exc}") from exc

    def get_by_metadata(self, where: dict[str, Any]) -> dict[str, Any]:
        """Lectura exacta por filtro de metadatos."""
        try:
            return self.collection.get(
                where=where,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo consultar por metadatos {where}: {exc}"
            ) from exc

    def source_is_current(self, source: str, document_hash: str) -> bool:
        """Indica si una versión exacta del archivo ya fue indexada."""
        records = self.get_by_metadata(
            {
                "$and": [
                    {"source": {"$eq": source}},
                    {"document_hash": {"$eq": document_hash}},
                ]
            }
        )
        return bool(records.get("ids"))

    def semantic_search(
        self,
        query_text: str,
        n_results: int = 4,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Vectoriza la consulta y recupera los chunks semánticamente cercanos."""
        if not query_text.strip():
            raise ValueError("La consulta no puede estar vacía.")

        total = self.count()
        if total == 0:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }

        query_args: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(n_results, total),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_args["where"] = where

        try:
            return self.collection.query(**query_args)
        except Exception as exc:
            raise RuntimeError(f"Falló la búsqueda semántica: {exc}") from exc

    def delete_by_ids(self, ids: list[str]) -> None:
        """Elimina chunks por ID."""
        if not ids:
            return
        try:
            self.collection.delete(ids=ids)
        except Exception as exc:
            raise RuntimeError(f"No se pudieron eliminar los IDs: {exc}") from exc

    def delete_by_metadata(self, where: dict[str, Any]) -> None:
        """Elimina todos los chunks que coinciden con un filtro."""
        try:
            self.collection.delete(where=where)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo eliminar por metadatos {where}: {exc}"
            ) from exc

    def indexed_sources(self) -> set[str]:
        """Lista los documentos fuente presentes en la colección."""
        try:
            records = self.collection.get(include=["metadatas"])
        except Exception as exc:
            raise RuntimeError(f"No se pudieron listar las fuentes: {exc}") from exc

        metadatas = records.get("metadatas") or []
        return {
            str(metadata["source"])
            for metadata in metadatas
            if metadata and metadata.get("source")
        }
