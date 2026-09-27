"""Recuperador híbrido: BM25 léxico + similitud en Pinecone, fusionados con RRF."""

from __future__ import annotations

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from config import settings
from documents import load_chunks
from ingest import vector_store

BM25_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6


class RAGSystem:
    """Encapsula el EnsembleRetriever y devuelve como máximo top-5 documentos."""

    def __init__(self, corpus: list[Document] | None = None) -> None:
        self.corpus = corpus if corpus is not None else load_chunks()
        self.lexical = BM25Retriever.from_documents(self.corpus)
        self.lexical.k = settings.top_k
        self.semantic = vector_store().as_retriever(
            search_kwargs={"k": settings.top_k, "namespace": settings.namespace}
        )
        self.ensemble = EnsembleRetriever(
            retrievers=[self.lexical, self.semantic],
            weights=[BM25_WEIGHT, VECTOR_WEIGHT],
        )

    def retrieve(self, query: str) -> list[Document]:
        """Combina coincidencia léxica y semántica sin sumar scores heterogéneos."""
        if not query.strip():
            raise ValueError("La consulta no puede estar vacía.")
        fused = self.ensemble.invoke(query)
        unique: list[Document] = []
        seen: set[tuple[str, int]] = set()
        for document in fused:
            identity = (
                str(document.metadata.get("document_id", "")),
                int(document.metadata.get("chunk_index", -1)),
            )
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(document)
            if len(unique) == settings.top_k:
                break
        return unique
